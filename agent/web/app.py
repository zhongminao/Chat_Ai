import asyncio
from contextlib import asynccontextmanager
import threading
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from ..core.session_registry import SessionRegistry
from ..core.session_runtime import SessionRuntime, SessionBusy
from ..model.discovery import refresh_catalog
from ..agentsessionstate.commands import SwitchModel
from ..agentsessionstate.input import UserInput
from .images import image_router
from .files import file_router
from .workspace_files import workspace_file_router
from ..storage.files import FileStore
from .events import session_events
from .history import history_page
from .shutdown import shutdown_signals


class SendMessageRequest(BaseModel):
    content: str = ""
    images: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)


class SwitchModelRequest(BaseModel):
    provider: str
    model: str


class UpdateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Omission is allowed; explicit null still fails validation of these non-null types.
    title: str = None
    pinned: StrictBool = None
    archived: StrictBool = None

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("需要提供 title、pinned 或 archived")
        return self


class GuidanceRequest(SendMessageRequest):
    message_id: str = Field(min_length=1, max_length=128)


class ApprovalDecisionRequest(BaseModel):
    approved: StrictBool


class AccessModeRequest(BaseModel):
    mode: Literal["audit", "full_access"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A fresh token per lifespan also supports repeated embedded/TestClient runs.
    app.state.stopping = threading.Event()
    catalog = getattr(registry, "catalog", None)
    # Finish initial discovery before accepting new sessions, so fallback selection
    # never mistakes an uninitialized directory for an offline default provider.
    if catalog:
        await asyncio.to_thread(refresh_catalog, catalog, timeout=2)
    with shutdown_signals(app.state.stopping):
        yield


app = FastAPI(title="chat_ai", lifespan=lifespan)
frontend_dist = Path(__file__).parent / "frontend" / "dist"
app.mount("/assets", StaticFiles(directory=frontend_dist / "assets", check_dir=False), name="assets")
registry = SessionRegistry()
session_store = registry.store


@app.exception_handler(SessionBusy)
@app.exception_handler(ValueError)
@app.exception_handler(FileNotFoundError)
async def business_error(request: Request, exc: Exception):
    missing = isinstance(exc, FileNotFoundError)
    detail = "Session not found" if missing and str(exc) == request.path_params.get("session_id") else str(exc)
    return JSONResponse(status_code=404 if missing else 409 if isinstance(exc, SessionBusy) else 400,
                        content={"detail": detail})


def directory_for(session_id: str) -> Path:
    return session_store.path(session_id)

def runtime(session_id: str) -> SessionRuntime:
    return registry.get(session_id)


app.include_router(image_router(session_store))
app.include_router(file_router(session_store))
app.include_router(workspace_file_router(registry.config.workspace))


@app.get("/")
def index():
    index_path = frontend_dist / "index.html"
    if not index_path.is_file():
        raise HTTPException(503, "Frontend not built. Run npm ci && npm run build in agent/web/frontend.")
    return FileResponse(index_path, headers={"Cache-Control": "no-cache"})


@app.post("/api/sessions")
def create():
    return {"id": registry.create().session.id}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    registry.delete(session_id)
    return {"deleted": True}


@app.patch("/api/sessions/{session_id}")
def update_session(session_id: str, request: UpdateSessionRequest):
    changes = session_store.update(session_id, **request.model_dump(exclude_unset=True))
    return {"id": session_id, **changes}


@app.get("/api/sessions")
def sessions():
    result = session_store.list_summaries()
    for item in result:
        rt = registry.items.get(item["id"])
        item["busy"] = bool(rt and rt.busy)
        if item["busy"]:
            item["status"] = "running"
    return {"sessions": result}


@app.get("/api/sessions/{session_id}/watch")
async def watch(session_id: str, cursor: int | None = None, timeout: float = Query(0, ge=0, le=30)):
    directory_for(session_id)
    return await asyncio.to_thread(registry.monitor(session_id).watch, cursor, timeout)


@app.get("/api/sessions/{session_id}/approvals")
def approvals(session_id: str):
    return runtime(session_id).approvals.snapshot()


@app.post("/api/sessions/{session_id}/approvals/{approval_id}")
def decide_approval(session_id: str, approval_id: str, request: ApprovalDecisionRequest):
    gate = runtime(session_id).approvals
    try:
        gate.resolve(approval_id, request.approved)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return gate.snapshot()


@app.post("/api/sessions/{session_id}/access")
def access_mode(session_id: str, request: AccessModeRequest):
    gate = runtime(session_id).approvals
    try:
        gate.set_mode(request.mode)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return gate.snapshot()


@app.get("/api/models")
def models():
    catalog = registry.catalog
    refresh_catalog(catalog, timeout=2)
    return {"defaultModel": catalog.new_session_default().as_dict(), "models": [
        {"provider": provider, "displayName": data.get("display_name", provider),
         "models": [{"id": item["id"], "name": item.get("name", item["id"]),
                    "enabled": item.get("enabled", True),
                    **{key: item[key] for key in ("reasoning_efforts", "default_reasoning_effort",
                                                    "api_default_reasoning_effort", "chat_completions",
                                                    "context_window", "input_modalities") if key in item}}
                    for item in catalog.models_for(provider)]}
        for provider, data in catalog.providers.items() if catalog.models_for(provider)
    ]}


@app.post("/api/sessions/{session_id}/model")
def switch_model(session_id: str, request: SwitchModelRequest):
    rt = runtime(session_id)
    with rt.lock:
        try:
            model = rt.dispatch(
                SwitchModel(provider=request.provider, model=request.model)
            )
        except RuntimeError as exc:
            raise HTTPException(400, str(exc))
    return {"model": model}


@app.post("/api/sessions/{session_id}/messages")
def send(session_id: str, message: SendMessageRequest):
    content = FileStore(directory_for(session_id)).format_message(message.content, message.files)
    runtime(session_id).enqueue(UserInput(content, tuple(message.images)))
    return {"accepted": True}


@app.post('/api/sessions/{session_id}/guidance')
def guide(session_id: str, message: GuidanceRequest):
    content = FileStore(directory_for(session_id)).format_message(message.content, message.files)
    runtime(session_id).send(UserInput(content, tuple(message.images)), message.message_id)
    return {'accepted': True}


@app.post("/api/sessions/{session_id}/control/stop")
def stop(session_id: str):
    return {"stopped": runtime(session_id).stop()}


@app.get("/api/sessions/{session_id}/history")
def history(session_id: str, before: int | None = Query(None, ge=1),
            through: int | None = Query(None, ge=0)):
    directory_for(session_id)
    if (before is None) != (through is None):
        raise HTTPException(400, "before and through must be supplied together")
    return history_page(session_store.open(session_id).events, before=before, through=through)


@app.get("/api/sessions/{session_id}/events")
async def events(session_id: str, request: Request, after: int = Query(0, ge=0)):
    rt = await asyncio.to_thread(runtime, session_id)
    try:
        cursor = int(request.headers.get('last-event-id', after))
        if cursor < 0:
            raise ValueError
    except ValueError:
        raise HTTPException(400, 'Last-Event-ID must be a non-negative integer') from None
    return StreamingResponse(
        session_events(rt, request, cursor, stopping=getattr(app.state, "stopping", None)), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )




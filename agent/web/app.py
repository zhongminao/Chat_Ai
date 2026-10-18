import asyncio
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool

from ..core.session_registry import SessionRegistry
from ..core.session_runtime import SessionRuntime, SessionBusy
from ..workflow.config import load
from ..model.catalog import ModelCatalog
from ..workflow.commands import SwitchModel
from ..workflow.input import UserInput
from .images import image_router
from .events import session_events


class SendMessageRequest(BaseModel):
    content: str = ""
    images: list[str] = Field(default_factory=list)


class SwitchModelRequest(BaseModel):
    provider: str
    model: str


class RenameSessionRequest(BaseModel):
    title: str


class GuidanceRequest(SendMessageRequest):
    message_id: str = Field(min_length=1, max_length=128)


class ApprovalDecisionRequest(BaseModel):
    approved: StrictBool


class AccessModeRequest(BaseModel):
    mode: Literal["audit", "full_access"]


app = FastAPI(title="chat_ai")
frontend_dist = Path(__file__).parent / "frontend" / "dist"
app.mount("/assets", StaticFiles(directory=frontend_dist / "assets", check_dir=False), name="assets")
registry = SessionRegistry()
session_store = registry.store


def directory_for(session_id: str) -> Path:
    try:
        return session_store.path(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found")

def runtime(session_id: str) -> SessionRuntime:
    try:
        return registry.get(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Session not found") from exc


app.include_router(image_router(session_store, runtime))


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
    try:
        registry.delete(session_id)
    except SessionBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, "Session not found") from exc
    return {"deleted": True}


@app.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, request: RenameSessionRequest):
    try:
        title = session_store.rename(session_id, request.title)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Session not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"id": session_id, "title": title}


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
    try:
        return await asyncio.to_thread(registry.monitor(session_id).watch, cursor, timeout)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


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
    catalog = ModelCatalog(load().providers_file)
    return {"models": [
        {"provider": provider, "displayName": data.get("display_name", provider),
         "models": [{"id": item["id"], "name": item.get("name", item["id"]),
                    "enabled": item.get("enabled", True)}
                    for item in data.get("models", [])]}
        for provider, data in catalog.providers.items()
    ]}


@app.post("/api/sessions/{session_id}/model")
def switch_model(session_id: str, request: SwitchModelRequest):
    rt = runtime(session_id)
    with rt.lock:
        try:
            model = rt.dispatch(
                SwitchModel(provider=request.provider, model=request.model)
            )
        except SessionBusy as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc))
    return {"model": model}


@app.post("/api/sessions/{session_id}/messages")
def send(session_id: str, message: SendMessageRequest):
    try:
        runtime(session_id).enqueue(UserInput(message.content, tuple(message.images)))
    except SessionBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"accepted": True}


@app.post('/api/sessions/{session_id}/guidance')
def guide(session_id: str, message: GuidanceRequest):
    try:
        runtime(session_id).send(UserInput(message.content, tuple(message.images)), message.message_id)
    except SessionBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {'accepted': True}


@app.post("/api/sessions/{session_id}/control/stop")
def stop(session_id: str):
    return {"stopped": runtime(session_id).stop()}


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
        session_events(rt, request, cursor), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )




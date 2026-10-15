import asyncio
import json
import queue
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..core.session_registry import SessionRegistry
from ..core.session_runtime import SessionRuntime, SessionBusy
from ..workflow.config import load
from ..model.catalog import ModelCatalog
from ..storage.event_log import EventLog
from ..workflow.history import restore_messages
from ..workflow.commands import SwitchModel
from ..workflow.input import UserInput
from ..storage.images import ImageStore
from .images import image_router


class Message(BaseModel):
    content: str = ""
    images: list[str] = Field(default_factory=list)


class ModelRequest(BaseModel):
    provider: str
    model: str


class SessionName(BaseModel):
    title: str


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
def rename_session(session_id: str, request: SessionName):
    try:
        title = session_store.rename(session_id, request.title)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Session not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"id": session_id, "title": title}


@app.get("/api/sessions")
def sessions():
    root = session_store.root
    result = []
    for directory in root.glob("*"):
        meta_path = directory / "session.json"
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        records = EventLog(directory / "events.jsonl").read()
        first_event = next((e for e in records if e["type"] == "turn.started"), {})
        first = first_event.get("prompt", "")
        rt = registry.items.get(directory.name)
        terminal = next((e for e in reversed(records) if e["type"] in
                         {"report.submitted", "turn.failed", "turn.cancelled"}), {})
        result.append({
            "id": directory.name,
            "parent_session_id": meta.get("parent_session_id"),
            "busy": bool(rt and rt.busy),
            "status": "running" if rt and rt.busy else {
                "report.submitted": "submitted", "turn.failed": "failed", "turn.cancelled": "cancelled",
            }.get(terminal.get("type"), "idle"),
            "title": meta.get("title") or " ".join(first.split())[:40] or ("图片对话" if first_event.get("images") else "新会话"),
            "empty": not bool(first_event),
            "createdAt": meta.get("createdAt"),
            "updatedAt": records[-1]["time"] / 1e9 if records else meta_path.stat().st_mtime,
        })
    result.sort(key=lambda item: item["updatedAt"], reverse=True)
    return {"sessions": result}


@app.get("/api/sessions/{session_id}/watch")
async def watch(session_id: str, cursor: int | None = None, timeout: float = Query(0, ge=0, le=30)):
    directory_for(session_id)
    try:
        return await asyncio.to_thread(registry.monitor(session_id).watch, cursor, timeout)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/sessions/{session_id}/conversation")
def conversation(session_id: str):
    records = EventLog(directory_for(session_id) / "events.jsonl").read()
    rt = registry.items.get(session_id)
    catalog = ModelCatalog(load().providers_file)
    meta = session_store.metadata(session_id)
    target = meta.get("model") or catalog.default().as_dict()
    for event in records:
        if event["type"] == "model.changed":
            target = event["new"]
    if rt and rt._agent is not None:
        target = rt.agent.state["model"]
    return {
        "id": session_id, "parent_session_id": meta.get("parent_session_id"), "messages": restore_messages(records),
        "seq": records[-1]["seq"] if records else 0,
        "busy": bool(rt and rt.busy), "model": target,
        "images": ImageStore(directory_for(session_id)).list(),
    }


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
def switch_model(session_id: str, request: ModelRequest):
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
def send(session_id: str, message: Message):
    try:
        runtime(session_id).enqueue(UserInput(message.content, tuple(message.images)))
    except SessionBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"accepted": True}


@app.post("/api/sessions/{session_id}/control/stop")
def stop(session_id: str):
    return {"stopped": runtime(session_id).stop()}


@app.get("/api/sessions/{session_id}/events")
async def events(session_id: str, request: Request, after: int = 0):
    rt = await asyncio.to_thread(runtime, session_id)
    channel = rt.bus.subscribe()

    async def stream():
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
        try:
            yield 'data: {"type":"connected"}\n\n'
            for event in rt.session.events.read(cursor):
                cursor = event["seq"]
                yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            ticks = 0
            while not await request.is_disconnected():
                try:
                    event = channel.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.1)
                    ticks += 1
                    if ticks >= 150:
                        yield ": heartbeat\n\n"
                        ticks = 0
                    continue
                if event["seq"] <= cursor:
                    continue
                cursor = event["seq"]
                yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            rt.bus.unsubscribe(channel)

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )




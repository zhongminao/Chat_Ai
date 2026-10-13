import asyncio
import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from ..workflow.config import load
from ..core.control import ControlState
from ..core.controller import Controller
from ..model.catalog import ModelCatalog
from ..storage.event_log import EventLog
from ..storage.session import SessionStore
from ..workflow.history import HistoryNode
from ..workflow.commands import SwitchModel
from ..tools.mcp.client import McpRuntime
from ..tools.router import ToolRouter
from .bus import EventBus


class Message(BaseModel):
    content: str


class ModelRequest(BaseModel):
    provider: str
    model: str


class Runtime:
    def __init__(self, directory: Path | None = None):
        config = load()
        self.bus = EventBus()
        self.session = (
            session_store.open(directory.name, self.bus.publish)
            if directory else session_store.create(self.bus.publish)
        )
        records = self.session.events.read()
        catalog = ModelCatalog(config.providers_file)
        target = catalog.default()
        for event in records:
            if event["type"] == "model.changed":
                target = catalog.resolve(event["new"]["provider"], event["new"]["name"])
        client, provider = catalog.runtime(target)
        tools = ToolRouter(config.workspace, McpRuntime(config.mcp) if config.mcp else None)
        self.control = ControlState()
        self.controller = Controller(
            client=client, model=target.as_dict(), provider=provider,
            catalog=catalog, thinking=target.thinking,
            session_id=self.session.id, spill=config.spill,
            workspace=config.workspace, log=self.session.events,
            output=lambda text: None,
            tools=tools,
            control=self.control,
        )
        self.controller.state = HistoryNode(records).run(self.controller.state)
        self.controller.messages.extend(self.controller.state["messages"])
        self.controller.state["messages"] = self.controller.messages
        self.queue = queue.Queue()
        self.busy = False
        self.lock = threading.Lock()
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, content: str):
        with self.lock:
            if self.busy:
                raise HTTPException(409, "This session is already running")
            self.control.clear_stop()
            self.busy = True
            self.queue.put(content)

    def stop(self) -> bool:
        with self.lock:
            if not self.busy:
                return False
            self.control.request_stop()
            return True

    def _worker(self):
        while True:
            content = self.queue.get()
            try:
                self.controller.run(content)
            except Exception as exc:
                self.session.events.append("turn.failed", reason=str(exc))
            finally:
                with self.lock:
                    self.busy = False
                self.queue.task_done()


app = FastAPI(title="chat_ai")
runtimes: dict[str, Runtime] = {}
runtime_lock = threading.Lock()
session_store = SessionStore(load().event_log.parent)


def directory_for(session_id: str) -> Path:
    try:
        return session_store.path(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found")

def runtime(session_id: str) -> Runtime:
    directory = directory_for(session_id)
    with runtime_lock:
        if session_id not in runtimes:
            runtimes[session_id] = Runtime(directory)
        return runtimes[session_id]


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.post("/api/sessions")
def create():
    with runtime_lock:
        rt = Runtime()
        runtimes[rt.session.id] = rt
    return {"id": rt.session.id}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    with runtime_lock:
        rt = runtimes.get(session_id)
        if rt and rt.busy:
            raise HTTPException(409, "This session is running")
        runtimes.pop(session_id, None)
        try:
            session_store.delete(session_id)
        except FileNotFoundError:
            raise HTTPException(404, "Session not found")
    return {"deleted": True}


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
        first = next((e["prompt"] for e in records if e["type"] == "turn.started"), "")
        result.append({
            "id": directory.name,
            "title": " ".join(first.split())[:40] or "新会话",
            "createdAt": meta.get("createdAt"),
            "updatedAt": records[-1]["time"] / 1e9 if records else meta_path.stat().st_mtime,
        })
    result.sort(key=lambda item: item["updatedAt"], reverse=True)
    return {"sessions": result}


@app.get("/api/sessions/{session_id}/conversation")
def conversation(session_id: str):
    records = EventLog(directory_for(session_id) / "events.jsonl").read()
    rt = runtimes.get(session_id)
    catalog = ModelCatalog(load().providers_file)
    target = catalog.default().as_dict()
    for event in records:
        if event["type"] == "model.changed":
            target = event["new"]
    if rt:
        target = rt.controller.model
    return {
        "id": session_id, "messages": HistoryNode(records).messages(),
        "seq": records[-1]["seq"] if records else 0,
        "busy": bool(rt and rt.busy), "model": target,
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
        if rt.busy:
            raise HTTPException(409, "This session is already running")
        try:
            model = rt.controller.dispatch(
                SwitchModel(provider=request.provider, model=request.model)
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc))
    return {"model": model}


@app.post("/api/sessions/{session_id}/messages")
def send(session_id: str, message: Message):
    if not message.content.strip():
        raise HTTPException(400, "Empty message")
    runtime(session_id).submit(message.content)
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




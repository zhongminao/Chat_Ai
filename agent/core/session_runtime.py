"""One serial inbox per session; different sessions execute independently."""
import json
import queue
import threading

from .agent_runtime import AgentRuntime
from .bus import EventBus
from .control import ControlState
from ..model.catalog import ModelCatalog
from ..model.messages import build_report_message
from ..storage.event_log import EventLog
from ..storage.session import SessionStore
from ..tools.mcp.client import McpRuntime
from ..tools.router import ToolRouter
from ..workflow.config import load
from ..workflow.history import HistoryNode
from ..workflow.input import UserInput


class SessionBusy(ValueError):
    pass


def session_result(session_id: str, records: list[dict]) -> dict:
    report = next((e for e in reversed(records) if e["type"] == "report.submitted"), None)
    if report:
        return {"session_id": session_id, "status": "submitted", "content": report["content"]}
    last = next((e for e in reversed(records) if e["type"] in {"turn.failed", "turn.cancelled"}), {})
    return {"session_id": session_id,
            "status": "cancelled" if last.get("type") == "turn.cancelled" else "failed",
            "content": last.get("reason", "Child execution was interrupted before submitting a report.")}


class SessionRuntime:
    def __init__(self, registry, session_id: str):
        self.registry = registry
        self.bus = EventBus()
        self.session = registry.store.open(session_id, self.bus.publish)
        self.meta = registry.store.metadata(session_id)
        self.parent_session_id = self.meta.get("parent_session_id")
        self.control = ControlState()
        self.lock = threading.RLock()
        self._agent_lock = threading.Lock()
        self._agent = None
        self._reports = {event["session_id"] for event in self.session.events.read()
                         if event["type"] == "report.received"}
        self.queue = queue.Queue()
        self.busy = False
        self.closed = False
        self.worker = threading.Thread(target=self._worker, daemon=True, name=f"session-{session_id[:8]}")
        self.worker.start()

    @property
    def agent(self) -> AgentRuntime:
        with self._agent_lock:
            if self._agent is None:
                self._agent = self.registry.agent_factory(self)
            return self._agent

    def enqueue(self, content: str | UserInput):
        with self.lock:
            if self.closed or self.parent_session_id:
                raise ValueError("Child sessions are read-only; create another child for a new task")
            if self.busy:
                raise SessionBusy("This session is already running")
            content = self.agent.prepare_input(content)
            self.control.clear_stop()
            self.busy = True
            self.queue.put(content)

    def stop(self) -> bool:
        with self.lock:
            if not self.busy:
                return False
            self.control.request_stop()
            return True

    def delegate(self, system_prompt: str, user_prompt: str) -> str:
        if not all(isinstance(value, str) and value.strip() for value in (system_prompt, user_prompt)):
            raise ValueError("system_prompt and user_prompt must be non-empty text")
        child = self.registry.create(parent_session_id=self.session.id,
                                     system_prompt=system_prompt.strip(), model=dict(self.agent.model),
                                     title=" ".join(user_prompt.split())[:40])
        self.session.events.append("agent.created", session_id=child.session.id)
        with child.lock:
            child.busy = True
            child.queue.put(UserInput(user_prompt))
        return json.dumps({"session_id": child.session.id}, ensure_ascii=False)

    def submitted(self, content: str, run_id: str):
        self.session.events.append("report.submitted", runId=run_id, content=content)

    def receive(self, report: dict):
        with self.lock:
            if self.closed or report["session_id"] in self._reports:
                return
            self._reports.add(report["session_id"])
            self.busy = True
            self.queue.put(report)

    def result(self) -> dict | None:
        if self.busy:
            return None
        return session_result(self.session.id, self.session.events.read())

    def _worker(self):
        while True:
            content = self.queue.get()
            if content is None:
                self.queue.task_done()
                return
            try:
                if isinstance(content, dict):
                    # Only the session worker writes its history and conversation.
                    agent = self.agent
                    self.session.events.append("report.received", **content)
                    agent.messages.append(build_report_message(content))
                    if self.control.is_requested("stop"):
                        continue
                    content = None
                self.agent.run(content)
                if self.parent_session_id and self.agent.submitted_report is None:
                    records = self.session.events.read()
                    if records[-1]["type"] != "turn.cancelled":
                        self.session.events.append("turn.failed", reason="Child ended without calling submit.")
            except Exception as exc:
                self.session.events.append("turn.failed", reason=str(exc))
            finally:
                if self.parent_session_id:
                    report = session_result(self.session.id, self.session.events.read())
                    self.registry.get(self.parent_session_id).receive(report)
                with self.lock:
                    self.busy = not self.queue.empty()
                self.queue.task_done()


def build_agent(runtime: SessionRuntime) -> AgentRuntime:
    config = runtime.registry.config
    records = runtime.session.events.read()
    catalog = ModelCatalog(config.providers_file)
    model = runtime.meta.get("model") or catalog.default().as_dict()
    for event in records:
        if event["type"] == "model.changed":
            model = event["new"]
    target = catalog.resolve(model["provider"], model["name"])
    client, provider = catalog.runtime(target)
    prompt = runtime.meta.get("system_prompt", config.system_prompt)
    if runtime.parent_session_id:
        prompt += ("\nYou are a child agent in an independent session. Complete the supplied task, "
                   "then call submit exactly once with your final report. Ordinary text does not "
                   "submit the task. Do not delegate. Include needed evidence and exact artifact paths.")
    tools = ToolRouter(config.workspace, McpRuntime(config.mcp) if config.mcp else None,
                       delegate=None if runtime.parent_session_id else runtime.delegate)
    agent = AgentRuntime(client=client, model=target.as_dict(), provider=provider, catalog=catalog,
                         thinking=target.thinking, session_id=runtime.session.id, spill=config.spill,
                         workspace=config.workspace, log=runtime.session.events, max_rounds=config.max_rounds,
                         system_prompt=prompt, output=lambda text: None, tools=tools,
                         control=runtime.control, on_submit=runtime.submitted)
    agent.messages.extend(HistoryNode(records).messages())
    agent.state["messages"] = agent.messages
    return agent


class SessionRuntimes:
    def __init__(self, config=None, *, agent_factory=build_agent):
        self.config = config or load()
        self.store = SessionStore(self.config.event_log.parent)
        self.agent_factory = agent_factory
        self.items: dict[str, SessionRuntime] = {}
        self.lock = threading.RLock()

    def get(self, session_id: str) -> SessionRuntime:
        with self.lock:
            if session_id in self.items:
                return self.items[session_id]
            runtime = SessionRuntime(self, session_id)
            self.items[session_id] = runtime
        # Recover finished/failed children after a service restart. Never rerun their work.
        if not runtime.parent_session_id:
            for child_id in self.store.children(session_id):
                child = self.items.get(child_id)
                if child and child.busy:
                    continue
                if child:
                    report = child.result()
                else:
                    records = EventLog(self.store.path(child_id) / "events.jsonl").read()
                    report = session_result(child_id, records)
                runtime.receive(report)
        return runtime

    def create(self, **metadata) -> SessionRuntime:
        return self.get(self.store.create(**metadata).id)

    def delete(self, session_id: str):
        with self.lock:
            if self.store.children(session_id):
                raise SessionBusy("Delete child sessions before deleting their main session")
            runtime = self.items.get(session_id)
            if runtime:
                with runtime.lock:
                    if runtime.busy:
                        raise SessionBusy("This session is running")
                    runtime.closed = True
                    runtime.queue.put(None)
            self.store.delete(session_id)
            self.items.pop(session_id, None)

    def wait(self):
        """Keep one-shot CLI alive until all sessions, including report handling, finish."""
        while True:
            with self.lock:
                current = list(self.items.values())
            for runtime in current:
                runtime.queue.join()
            with self.lock:
                if len(current) == len(self.items) and not any(rt.busy for rt in self.items.values()):
                    return

"""Session lookup, child creation and the agent producer for the generic monitor."""
import json
import threading
from pathlib import Path

from .monitor import Monitor
from .session_runtime import SessionBusy, SessionRuntime
from ..storage.session import SessionStore
from ..storage import reports
from ..workflow.config import load
from ..workflow.input import UserInput


class SessionRegistry:
    def __init__(self, config=None):
        self.config = config or load()
        self.store = SessionStore(self.config.storage_dir)
        self.items: dict[str, SessionRuntime] = {}
        self.monitors: dict[str, Monitor] = {}
        self.lock = threading.RLock()

    def get(self, session_id: str) -> SessionRuntime:
        with self.lock:
            if session_id not in self.items:
                self.items[session_id] = SessionRuntime(self, session_id)
            return self.items[session_id]

    def create(self, **metadata) -> SessionRuntime:
        return self.get(self.store.create(**metadata).id)

    def monitor(self, session_id: str) -> Monitor:
        with self.lock:
            if session_id not in self.monitors:
                self.store.path(session_id)
                monitor = Monitor(self.store, session_id)
                for child_id in self.store.children(session_id):
                    child = self.items.get(child_id)
                    state = {"kind": "agent", "session_id": child_id,
                             "title": self.store.metadata(child_id).get("title", "子 agent")}
                    if child and child.busy:
                        state["status"] = "running"
                    else:
                        state.update(self._result(child_id))
                    monitor.update(f"agent:{child_id}", **state)
                self.monitors[session_id] = monitor
            return self.monitors[session_id]

    def _result(self, session_id: str) -> dict:
        session = self.store.open(session_id)
        records = session.events.read()
        submitted = next((e for e in reversed(records) if e["type"] == "report.submitted"), None)
        if submitted:
            path = Path(submitted.get("result_path", ""))
            if not path.is_file():
                path, _ = reports.save(session, submitted.get("runId") or str(submitted["seq"]),
                                       submitted["content"], self.config.workspace)
            return {"status": "completed", "result_path": str(path.resolve())}
        last = next((e for e in reversed(records) if e["type"] in {"turn.failed", "turn.cancelled"}), {})
        return {"status": "cancelled" if last.get("type") == "turn.cancelled" else "failed",
                "error": last.get("reason", "Execution was interrupted before submitting a report.")}

    def delegate(self, parent_id: str, user_prompt: str) -> str:
        if not isinstance(user_prompt, str) or not user_prompt.strip():
            raise ValueError("user_prompt must be non-empty text")
        parent = self.get(parent_id)
        monitor = self.monitor(parent_id)
        child = self.create(parent_session_id=parent_id,
                            model=dict(parent.state["model"]), title=" ".join(user_prompt.split())[:40])
        monitor.update(f"agent:{child.session.id}", kind="agent", session_id=child.session.id,
                       title=child.meta["title"], status="running")
        execution = parent.state["execution"]
        parent.session.events.append("agent.created", session_id=child.session.id,
                                     runId=execution["id"] if execution else None)
        child.start(UserInput(user_prompt))
        return json.dumps({"id": f"agent:{child.session.id}", "session_id": child.session.id,
                           "status": "running", "hint": "子任务已在后台独立运行。需要查看状态时调用 watch() 获取全部资源快照。"
                           "返回的 cursor 是当前主会话全部监控资源的版本号，不是 agent 编号；"
                           "等待变化时原样传入最近一次 watch 的 cursor：watch(cursor=<返回值>, timeout=60)。"
                           "每次使用最新返回的 cursor；超时没有变化时保持不变。"
                           "completed 时用 read_file 读取 result_path；failed/cancelled 时按 error 判断原因。"
                           "停止当前回复不会停止子任务；结果不会自动写入主对话。"}, ensure_ascii=False)

    def finished(self, child: SessionRuntime):
        self.monitor(child.parent_session_id).update(
            f"agent:{child.session.id}", kind="agent", session_id=child.session.id,
            title=child.meta.get("title", "子 agent"), **self._result(child.session.id))

    def delete(self, session_id: str):
        with self.lock:
            if self.store.children(session_id):
                raise SessionBusy("Delete child sessions before deleting their main session")
            meta = self.store.metadata(session_id)
            runtime = self.items.get(session_id)
            if runtime:
                with runtime.lock:
                    if runtime.busy:
                        raise SessionBusy("This session is running")
                    runtime.closed = True
                    runtime.queue.put(None)
            self.store.delete(session_id)
            self.items.pop(session_id, None)
            self.monitors.pop(session_id, None)
            if parent_id := meta.get("parent_session_id"):
                self.monitor(parent_id).remove(f"agent:{session_id}")

    def wait(self):
        """A one-shot CLI process must stay alive for its background children."""
        while True:
            with self.lock:
                current = list(self.items.values())
            for runtime in current:
                runtime.queue.join()
            with self.lock:
                if len(current) == len(self.items) and not any(rt.busy for rt in self.items.values()):
                    return

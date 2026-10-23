"""Session lookup, child creation and the agent producer for the generic monitor."""
import json
import threading
from contextlib import ExitStack
from pathlib import Path

from .monitor import Monitor
from .session_runtime import SessionBusy, SessionRuntime
from ..storage.session import SessionStore
from ..storage.agent_to_agent_mailbox import AgentToAgentMailbox
from ..storage import reports
from ..workflow.config import load
from ..workflow.input import UserInput
from ..model.catalog import ModelCatalog


class SessionRegistry:
    def __init__(self, config=None):
        self.config = config or load()
        self.catalog = ModelCatalog(self.config.providers_file)
        self.store = SessionStore(self.config.storage_dir)
        self.mailbox = AgentToAgentMailbox(self.store.database)
        self.items: dict[str, SessionRuntime] = {}
        self.monitors: dict[str, Monitor] = {}
        self.lock = threading.RLock()

    def get(self, session_id: str) -> SessionRuntime:
        with self.lock:
            if session_id not in self.items:
                self.items[session_id] = SessionRuntime(self, session_id)
            return self.items[session_id]

    def create(self, **metadata) -> SessionRuntime:
        with self.lock:
            if not metadata.get("parent_session_id") and not metadata.get("model"):
                metadata["model"] = self.catalog.new_session_default().as_dict()
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
                "error": last.get("reason", "Execution was interrupted before submitting a report."),
                "events_path": str(session.events.path.resolve())}

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
                           "等待变化时原样传入最近一次 watch 的 cursor，timeout 按需要选择，最多 86400 秒（1 天）；有变化会提前返回。"
                           "每次使用最新返回的 cursor；超时没有变化时保持不变。"
                           "completed 时用 read_file 读取 result_path；failed/cancelled 时检查 error，并用 read_file 读取 events_path 核对已执行工作，再决定后续处理。"
                           "停止当前回复不会停止子任务；结果不会自动写入主对话。"}, ensure_ascii=False)

    def finished(self, child: SessionRuntime):
        self.monitor(child.parent_session_id).update(
            f"agent:{child.session.id}", kind="agent", session_id=child.session.id,
            title=child.meta.get("title", "子 agent"), **self._result(child.session.id))

    def _mailbox_resource(self, session_id: str) -> None:
        self.monitor(session_id).update(
            f"mailbox:{session_id}", kind="mailbox", session_id=session_id,
            unread_count=self.mailbox.unread_count(session_id),
            latest_id=self.mailbox.latest_id(session_id))

    def notify_agent(self, sender_id: str, recipient_id: str, content: str,
                     cc=(), kind='notification') -> dict:
        """Call with the authenticated runtime's sender ID, never a model-supplied ID."""
        if not isinstance(recipient_id, str) or not recipient_id:
            raise ValueError("recipient must be a session ID")
        if not isinstance(cc, (list, tuple)) or not all(isinstance(item, str) for item in cc):
            raise ValueError("cc must be a sequence of session IDs")
        cc = tuple(cc)
        # Lock all target runtimes in stable order against concurrent submit/stop.
        with self.lock, ExitStack() as locks:
            targets = sorted(set((recipient_id, *cc)))
            for target in targets:
                runtime = self.get(target)
                locks.enter_context(runtime.lock)
                if runtime.parent_session_id and (runtime.closed or runtime.submitting or
                                                  not runtime.busy or not runtime.steering.accepting or
                                                  runtime.control.stopped):
                    raise SessionBusy('子 agent 正在提交或停止，无法投递留言')
            result = self.mailbox.send(sender_id, recipient_id, content, cc=cc, kind=kind)
            for target in targets:
                self._mailbox_resource(target)
            return result

    def mailbox_list(self, session_id: str, unread_only: bool = False) -> list[dict]:
        return self.mailbox.list(session_id, unread_only)

    def mailbox_read(self, session_id: str, message_id: str) -> dict:
        result = self.mailbox.read(session_id, message_id)
        self._mailbox_resource(session_id)
        return result

    def mailbox_unread_count(self, session_id: str) -> int:
        return self.mailbox.unread_count(session_id)

    def delete(self, session_id: str):
        with self.lock, ExitStack() as locks:
            meta = self.store.metadata(session_id)
            children = self.store.children(session_id)
            identifiers = [*children, session_id]
            runtimes = [self.items[key] for key in identifiers if key in self.items]
            for runtime in runtimes:
                locks.enter_context(runtime.lock)
            if any(runtime.busy for runtime in runtimes):
                raise SessionBusy("主会话或子任务正在运行，请先停止后再删除。")
            self.store.delete(session_id, children=children)
            for runtime in runtimes:
                runtime.closed = True
                runtime.queue.put(None)
            for identifier in identifiers:
                self.items.pop(identifier, None)
                self.monitors.pop(identifier, None)
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

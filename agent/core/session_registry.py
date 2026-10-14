"""Session lookup, child creation and the agent producer for the generic monitor."""
import json
import threading
from functools import partial
from pathlib import Path

from .agent_runtime import AgentRuntime
from .monitor import Monitor
from .session_runtime import SessionBusy, SessionRuntime
from ..model.catalog import ModelCatalog
from ..storage.session import SessionStore
from ..storage import reports
from ..tools.mcp.client import McpRuntime
from ..tools.router import ToolRouter
from ..workflow.config import load
from ..workflow.history import HistoryNode
from ..workflow.input import UserInput


class SessionRuntimes:
    def __init__(self, config=None):
        self.config = config or load()
        self.store = SessionStore(self.config.event_log.parent)
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
                monitor = Monitor(self.store.path(session_id) / "watch.json")
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

    def delegate(self, parent_id: str, system_prompt: str, user_prompt: str) -> str:
        if not all(isinstance(value, str) and value.strip() for value in (system_prompt, user_prompt)):
            raise ValueError("system_prompt and user_prompt must be non-empty text")
        parent = self.get(parent_id)
        monitor = self.monitor(parent_id)
        child = self.create(parent_session_id=parent_id, system_prompt=system_prompt.strip(),
                            model=dict(parent.agent.model), title=" ".join(user_prompt.split())[:40])
        monitor.update(f"agent:{child.session.id}", kind="agent", session_id=child.session.id,
                       title=child.meta["title"], status="running")
        parent.session.events.append("agent.created", session_id=child.session.id,
                                     runId=getattr(parent.agent, "_current_run_id", None))
        child.start(UserInput(user_prompt))
        return json.dumps({"id": f"agent:{child.session.id}", "session_id": child.session.id,
                           "status": "running", "hint": "已纳入 watch 监控。先调用 watch() 获取快照；"
                           "再用返回的 cursor 和 timeout>0 等待变化。完成后用 read_file 读取 result_path。"}, ensure_ascii=False)

    def finished(self, child: SessionRuntime):
        self.monitor(child.parent_session_id).update(
            f"agent:{child.session.id}", kind="agent", session_id=child.session.id,
            title=child.meta.get("title", "子 agent"), **self._result(child.session.id))

    def build_agent(self, runtime: SessionRuntime) -> AgentRuntime:
        config = self.config
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
            prompt += ("\nYou are an independent child agent. Complete the task and call submit exactly once "
                       "with your final Markdown report. Ordinary text does not submit it. Use show_image "
                       "to publish images and retain its Markdown URLs and local image paths in the report.")
        else:
            prompt += ("\nAt the start of each user request, query watch() for background resources. "
                       "Delegate independent work with delegate; it keeps running after your turn ends. "
                       "Use watch(cursor=<last watch cursor>, timeout=60) when waiting for changes. "
                       "A completed resource contains result_path; read it with read_file when useful. "
                       "Decide whether results are sufficient, whether to keep working, or wait again. "
                       "\n普通问答、澄清和进度说明直接回复，无需调用 submit。"
                       "完成复杂任务后，若需要收起较长的分析和工具执行过程，再调用 submit 提交整理后的最终结论。"
                       "网页会将本轮此前的过程默认折叠，只展示 submit 内容。"
                       "submit 会结束本轮执行，应单独调用，内容须完整、可独立阅读，不必重复过程。\n"
                       "Reuse exact Markdown image URLs from reports to display their images, and use the "
                       "local image_file paths with read_image if you need to inspect them.")
        tools = ToolRouter(config.workspace, McpRuntime(config.mcp) if config.mcp else None,
                           delegate=None if runtime.parent_session_id else partial(self.delegate, runtime.session.id),
                           watch=None if runtime.parent_session_id else self.monitor(runtime.session.id).watch)
        agent = AgentRuntime(client=client, model=target.as_dict(), provider=provider, catalog=catalog,
                             thinking=target.thinking, session_id=runtime.session.id, spill=config.spill,
                             workspace=config.workspace, log=runtime.session.events, max_rounds=config.max_rounds,
                             system_prompt=prompt, output=lambda text: None, tools=tools,
                             control=runtime.control, on_submit=runtime.submitted)
        agent.messages.extend(HistoryNode(records).messages())
        agent.state["messages"] = agent.messages
        return agent

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

"""A session owns one execution queue and one independent cancellation scope."""
import queue
import threading
import uuid

from .bus import EventBus
from .control import ExecutionControl
from .steering import SteeringQueue
from .agent_factory import build_agent, build_state
from ..storage import reports
from ..model.catalog import ModelCatalog
from ..workflow.commands import SwitchModel
from ..workflow.state import AgentState, StateUpdate
from ..workflow import transitions
from ..tools.approval import ApprovalGate


class SessionBusy(ValueError):
    pass


class SessionRuntime:
    def __init__(self, registry, session_id: str):
        self.registry = registry
        self.bus = EventBus()
        self.session = registry.store.open(session_id, self.bus.publish)
        self.meta = registry.store.metadata(session_id)
        self.parent_session_id = self.meta.get("parent_session_id")
        if self.parent_session_id:
            self.approvals = registry.get(self.parent_session_id).approvals
        else:
            mode = next((e["mode"] for e in reversed(self.session.events.read())
                         if e["type"] == "approval.mode.changed"), registry.config.approval_mode)
            self.approvals = ApprovalGate(mode, self.session.events.append)
        self.control = ExecutionControl()
        self.lock = threading.RLock()
        self.steering = SteeringQueue(self.lock, self.session.events.append, self.session.events.read())
        self._agent_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._state: AgentState | None = None
        self._agent = None
        self.queue = queue.Queue()
        self.busy = False
        self.closed = False
        self.worker = threading.Thread(target=self._worker, daemon=True, name=f"session-{session_id[:8]}")
        self.worker.start()

    @property
    def state(self) -> AgentState:
        with self._state_lock:
            if self._state is None:
                self._state = build_state(self.registry.config, self.meta, self.session.events.read())
            return self._state

    def apply(self, update: StateUpdate) -> None:
        self.state.update(update)

    def dispatch(self, command: SwitchModel) -> dict:
        with self.lock:
            if self.busy or self.parent_session_id:
                raise SessionBusy('This session is running or is a read-only child session')
            catalog = self._agent.catalog if self._agent else ModelCatalog(self.registry.config.providers_file)
            target = catalog.resolve(command.provider, command.model)
            old = self.state['model']
            self.apply(transitions.switch_model(self.state, target.as_dict()))
            self.session.events.append('model.changed', old=old, new=self.state['model'])
            return self.state['model']

    @property
    def agent(self):
        with self._agent_lock:
            if self._agent is None:
                self._agent = build_agent(self)
            return self._agent

    def enqueue(self, content):
        if self.parent_session_id:
            raise ValueError("Child sessions are read-only; delegate another task instead")
        self.start(self.agent.prepare_input(content))

    def send(self, content, message_id=None):
        """CLI sends immediately; Web calls this only after clicking Guide."""
        if self.parent_session_id:
            raise ValueError('子会话只供查看')
        value = self.agent.prepare_input(content)
        with self.lock:
            if self.closed:
                raise SessionBusy('会话已关闭')
            if message_id in self.steering.received:
                self.steering.add(message_id, value, [])
                return
            if self.busy:
                if not self.steering.accepting:
                    raise SessionBusy('正在停止或结束，请稍后重试')
                assets = [self.agent.images.get(image) for image in value.images]
                self.steering.add(message_id or uuid.uuid4().hex, value, assets)
            else:
                self.start(value)
                if message_id:
                    self.steering.received[message_id] = value

    def start(self, content):
        with self.lock:
            if self.closed or self.busy:
                raise SessionBusy("This session is closed or already running")
            self.control.clear_stop()
            self.steering.begin()
            self.busy = True
            self.queue.put(content)

    def stop(self) -> bool:
        with self.lock:
            if not self.busy:
                return False
            self.control.request_stop()
            self.steering.close()
            return True

    def submitted(self, content: str, run_id: str) -> str:
        path, rendered = reports.save(self.session, run_id, content, self.registry.config.workspace)
        self.apply(transitions.report_saved(self.state, rendered, str(path)))
        self.session.events.append("report.submitted", runId=run_id, content=rendered, result_path=str(path))
        return rendered

    def _worker(self):
        while True:
            content = self.queue.get()
            if content is None:
                try:
                    if self._agent is not None:
                        self._agent.close()
                finally:
                    self.queue.task_done()
                return
            try:
                self.agent.run(content)
            except Exception as exc:
                self.session.events.append("turn.failed", reason=str(exc))
            finally:
                try:
                    if self.parent_session_id:
                        self.registry.finished(self)
                finally:
                    with self.lock:
                        self.steering.close()
                        self.busy = False
                    self.queue.task_done()

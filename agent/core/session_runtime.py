"""A session owns one execution queue and one independent cancellation scope."""
import queue
import threading

from .bus import EventBus
from .control import ExecutionControl
from ..storage import reports
from ..model.catalog import ModelCatalog
from ..workflow.commands import SwitchModel
from ..workflow.state import AgentState, StateUpdate
from ..workflow import transitions


class SessionBusy(ValueError):
    pass


class SessionRuntime:
    def __init__(self, registry, session_id: str):
        self.registry = registry
        self.bus = EventBus()
        self.session = registry.store.open(session_id, self.bus.publish)
        self.meta = registry.store.metadata(session_id)
        self.parent_session_id = self.meta.get("parent_session_id")
        self.control = ExecutionControl()
        self.lock = threading.RLock()
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
                self._state = self.registry.build_state(self)
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
                self._agent = self.registry.build_agent(self)
            return self._agent

    def enqueue(self, content):
        if self.parent_session_id:
            raise ValueError("Child sessions are read-only; delegate another task instead")
        self.start(self.agent.prepare_input(content))

    def start(self, content):
        with self.lock:
            if self.closed or self.busy:
                raise SessionBusy("This session is closed or already running")
            self.control.clear_stop()
            self.busy = True
            self.queue.put(content)

    def stop(self) -> bool:
        with self.lock:
            if not self.busy:
                return False
            self.control.request_stop()
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
                self.queue.task_done()
                return
            try:
                self.agent.run(content)
                execution = self.state["execution"]
                if self.parent_session_id and execution["report"] is None and execution["status"] != "cancelled":
                    reason = "Child ended without calling submit."
                    self.apply(transitions.fail(self.state, reason))
                    self.session.events.append("turn.failed", reason=reason)
            except Exception as exc:
                self.session.events.append("turn.failed", reason=str(exc))
            finally:
                try:
                    if self.parent_session_id:
                        self.registry.finished(self)
                finally:
                    with self.lock:
                        self.busy = False
                    self.queue.task_done()

"""A session owns one execution queue and one independent cancellation scope."""
import queue
import threading

from .bus import EventBus
from .control import ControlState
from ..storage import reports


class SessionBusy(ValueError):
    pass


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
        self.queue = queue.Queue()
        self.busy = False
        self.closed = False
        self.worker = threading.Thread(target=self._worker, daemon=True, name=f"session-{session_id[:8]}")
        self.worker.start()

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
                if self.parent_session_id and self.agent.submitted_report is None:
                    records = self.session.events.read()
                    if records[-1]["type"] != "turn.cancelled":
                        self.session.events.append("turn.failed", reason="Child ended without calling submit.")
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

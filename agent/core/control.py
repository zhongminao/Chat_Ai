from threading import Lock

from .cancellation import CancellationToken


class ExecutionControl:
    def __init__(self):
        self._signals: set[str] = set()
        self._active: CancellationToken | None = None
        self._lock = Lock()

    def request_stop(self) -> None:
        with self._lock:
            self._signals.add("stop")
            token = self._active
        if token:
            token.cancel()

    @property
    def stopped(self) -> bool:
        with self._lock:
            return "stop" in self._signals

    def clear_stop(self) -> None:
        with self._lock:
            self._signals.discard("stop")

    def bind(self, token: CancellationToken) -> None:
        with self._lock:
            self._active = token
            stopped = "stop" in self._signals
        if stopped:
            token.cancel()

    def unbind(self, token: CancellationToken) -> None:
        with self._lock:
            if self._active is token:
                self._active = None

from threading import Lock

from .cancellation import CancellationToken


CONTROL_ORDER = ["stop"]


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

    def clear_stop(self) -> None:
        with self._lock:
            self._signals.discard("stop")

    def is_requested(self, name: str) -> bool:
        with self._lock:
            return name in self._signals

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

    def pending(self) -> list[str]:
        with self._lock:
            signals = set(self._signals)
        return [name for name in CONTROL_ORDER if name in signals]

    def consume(self) -> str | None:
        """Compatibility helper; stop remains requested until cleared explicitly."""
        with self._lock:
            for name in CONTROL_ORDER:
                if name in self._signals:
                    return name
        return None

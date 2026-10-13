from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock
from typing import Callable


class RunCancelled(Exception):
    """Raised when the current agent run is cancelled."""


class CancellationToken:
    def __init__(self):
        self._event = Event()
        self._lock = Lock()
        self._callbacks: list[Callable[[], None]] = []

    def cancel(self) -> None:
        with self._lock:
            if self._event.is_set():
                return
            self._event.set()
            callbacks = list(self._callbacks)
            self._callbacks.clear()
        for callback in callbacks:
            try:
                callback()
            except Exception:
                pass

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise RunCancelled()

    def add_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        with self._lock:
            if self._event.is_set():
                run_now = True
            else:
                self._callbacks.append(callback)
                run_now = False

        if run_now:
            try:
                callback()
            except Exception:
                pass
            return lambda: None

        def remove() -> None:
            with self._lock:
                try:
                    self._callbacks.remove(callback)
                except ValueError:
                    pass

        return remove


@dataclass(frozen=True)
class ExecutionContext:
    cancellation: CancellationToken

"""Versioned resource snapshots. Producers update; consumers query or wait."""
import threading
import time

from .cancellation import ExecutionContext
from ..storage.session import SessionStore


class Monitor:
    def __init__(self, store: SessionStore, session_id: str):
        self.store, self.session_id = store, session_id
        saved = store.read_monitor(session_id)
        self.version = saved.get("cursor", 0)
        self.resources = saved.get("resources", {})
        self.condition = threading.Condition()

    def update(self, identifier: str, **state) -> None:
        with self.condition:
            while True:
                saved = self.store.read_monitor(self.session_id)
                self.version, self.resources = saved.get("cursor", 0), saved.get("resources", {})
                old = self.resources.get(identifier, {})
                value = {"id": identifier, **state}
                if {key: item for key, item in old.items() if key != "version"} == value:
                    return
                version = self.version + 1
                resources = {**self.resources, identifier: {**value, "version": version}}
                if self.store.save_monitor(self.session_id, version, resources):
                    self.version, self.resources = version, resources
                    self.condition.notify_all()
                    return

    def remove(self, identifier: str) -> None:
        self.update(identifier, deleted=True)

    def _wake(self) -> None:
        with self.condition:
            self.condition.notify_all()

    def watch(self, cursor: int | None = None, timeout: float = 0,
              context: ExecutionContext | None = None) -> dict:
        if cursor is not None and (type(cursor) is not int or cursor < 0):
            raise ValueError("cursor must be a non-negative integer or null")
        if not isinstance(timeout, (int, float)) or not 0 <= timeout <= 86400:
            raise ValueError("timeout must be between 0 and 86400 seconds")
        deadline = time.monotonic() + timeout
        remove_callback = context.cancellation.add_callback(self._wake) if context else lambda: None
        try:
            with self.condition:
                while True:
                    saved = self.store.read_monitor(self.session_id)
                    if saved.get("cursor", 0) > self.version:
                        self.version = saved["cursor"]
                        self.resources = saved["resources"]
                    if cursor is not None and cursor > self.version:
                        raise ValueError("cursor is ahead of this monitor; call watch() for a fresh snapshot")
                    if context:
                        context.cancellation.raise_if_cancelled()
                    if cursor is None or self.version > cursor or time.monotonic() >= deadline:
                        break
                    self.condition.wait(min(1, max(0, deadline - time.monotonic())))
                changes = [dict(value) for value in self.resources.values()
                           if (not value.get("deleted") if cursor is None else value["version"] > cursor)]
                return {"cursor": self.version, "changes": changes}
        finally:
            remove_callback()

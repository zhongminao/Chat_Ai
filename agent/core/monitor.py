"""Versioned resource snapshots and opt-in, live read receipts."""
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
        lock = threading.RLock()
        self.condition = threading.Condition(lock)
        self._detailed_condition = threading.Condition(lock)
        self._receipt_waiters: dict[object, tuple[float, list[tuple[str, str]]]] = {}

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
                    self._notify_waiters()
                    return

    def remove(self, identifier: str) -> None:
        self.update(identifier, deleted=True)

    def _notify_waiters(self) -> None:
        # Both conditions share the lock, but receipts notify only detailed watches.
        self.condition.notify_all()
        self._detailed_condition.notify_all()

    def _wake(self) -> None:
        with self.condition:
            self._notify_waiters()

    def record_read_receipt(self, message_id: str, recipient_id: str) -> None:
        """Publish a committed acknowledgement to this sender's current detailed watches."""
        with self._detailed_condition:
            now = time.monotonic()
            for deadline, receipts in self._receipt_waiters.values():
                if now < deadline:
                    receipts.append((message_id, recipient_id))
            if self._receipt_waiters:
                self._detailed_condition.notify_all()

    def watch(self, cursor: int | None = None, timeout: float = 0,
              context: ExecutionContext | None = None, *, wake_if=None,
              detail_level: str = "default") -> dict:
        if cursor is not None and (type(cursor) is not int or cursor < 0):
            raise ValueError("cursor must be a non-negative integer or null")
        if not isinstance(timeout, (int, float)) or not 0 <= timeout <= 86400:
            raise ValueError("timeout must be between 0 and 86400 seconds")
        if detail_level not in ("default", "detailed"):
            raise ValueError("detail_level must be default or detailed")
        deadline = time.monotonic() + timeout
        detailed = detail_level == "detailed"
        condition = self._detailed_condition if detailed else self.condition
        with condition:
            waiter, receipts = object(), []
            remove_callback = None
            try:
                if context:
                    remove_callback = context.cancellation.add_callback(self._wake)
                while True:
                    saved = self.store.read_monitor(self.session_id)
                    if saved.get("cursor", 0) > self.version:
                        self.version = saved["cursor"]
                        self.resources = saved["resources"]
                    if cursor is not None and cursor > self.version:
                        raise ValueError("cursor is ahead of this monitor; call watch() for a fresh snapshot")
                    if context:
                        context.cancellation.raise_if_cancelled()
                    if cursor is None or self.version > cursor or receipts or time.monotonic() >= deadline:
                        break
                    if wake_if and wake_if():
                        break
                    if detailed:
                        self._receipt_waiters[waiter] = (deadline, receipts)
                    condition.wait(min(1, max(0, deadline - time.monotonic())))
                changes = [dict(value) for value in self.resources.values()
                           if (not value.get("deleted") if cursor is None else value["version"] > cursor)]
                result = {"cursor": self.version, "changes": changes}
                if cursor is not None and wake_if and wake_if():
                    result["interrupted_by_guidance"] = True
                if receipts:
                    result["read_receipts"] = [{"message_id": message_id, "recipient_id": recipient_id}
                                               for message_id, recipient_id in receipts]
                return result
            finally:
                if detailed:
                    self._receipt_waiters.pop(waiter, None)
                if remove_callback:
                    remove_callback()

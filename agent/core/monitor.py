"""Versioned resource snapshots. Producers update; consumers query or wait."""
import json
import threading
import time
from pathlib import Path

from .cancellation import ExecutionContext


class Monitor:
    def __init__(self, path: Path):
        self.path = path
        saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.version = saved.get("cursor", 0)
        self.resources = saved.get("resources", {})
        self.condition = threading.Condition()

    def update(self, identifier: str, **state) -> None:
        with self.condition:
            old = self.resources.get(identifier, {})
            value = {"id": identifier, **state}
            if {key: item for key, item in old.items() if key != "version"} == value:
                return
            version = self.version + 1
            resources = {**self.resources, identifier: {**value, "version": version}}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"cursor": version, "resources": resources},
                                             ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(self.path)
            self.version, self.resources = version, resources
            self.condition.notify_all()

    def remove(self, identifier: str) -> None:
        self.update(identifier, deleted=True)

    def _wake(self) -> None:
        with self.condition:
            self.condition.notify_all()

    def watch(self, cursor: int | None = None, timeout: float = 0,
              context: ExecutionContext | None = None) -> dict:
        if cursor is not None and (type(cursor) is not int or cursor < 0):
            raise ValueError("cursor must be a non-negative integer or null")
        if not isinstance(timeout, (int, float)) or not 0 <= timeout <= 120:
            raise ValueError("timeout must be between 0 and 120 seconds")
        deadline = time.monotonic() + timeout
        remove_callback = context.cancellation.add_callback(self._wake) if context else lambda: None
        try:
            with self.condition:
                if cursor is not None and cursor > self.version:
                    raise ValueError("cursor is ahead of this monitor; call watch() for a fresh snapshot")
                while True:
                    if context:
                        context.cancellation.raise_if_cancelled()
                    if cursor is None or self.version > cursor or time.monotonic() >= deadline:
                        break
                    self.condition.wait(max(0, deadline - time.monotonic()))
                changes = [dict(value) for value in self.resources.values()
                           if (not value.get("deleted") if cursor is None else value["version"] > cursor)]
                return {"cursor": self.version, "changes": changes}
        finally:
            remove_callback()

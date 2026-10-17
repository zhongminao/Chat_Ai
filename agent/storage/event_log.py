import json
import os
import time
from threading import RLock
from pathlib import Path
from typing import Any, Callable


class EventLog:
    def __init__(
        self,
        path: Path,
        on_append: Callable[[dict[str, Any]], None] | None = None,
    ):
        self._lock = RLock()
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.sequence = self._last_sequence()
        self.on_append = on_append

    def _last_sequence(self) -> int:
        if not self.path.exists():
            return 0
        last = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                last = int(json.loads(line)["seq"])
            except (KeyError, ValueError, json.JSONDecodeError):
                continue
        return last

    def append(
        self,
        event_type: str,
        *,
        durable: bool = True,
        **data: Any,
    ) -> dict[str, Any]:
        with self._lock:
            self.sequence += 1
            record = {
                "seq": self.sequence,
                "time": time.time_ns(),
                "type": event_type,
                **data,
            }
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
                file.flush()
                if durable:
                    os.fsync(file.fileno())
            if self.on_append:
                self.on_append(record)
            return record

    def read(self, after: int = 0) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            record
            for line in self.path.read_text(encoding="utf-8").splitlines(keepends=True)
            if line.endswith("\n")
            for record in [json.loads(line)]
            if int(record["seq"]) > after
        ]

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .event_log import EventLog


@dataclass(frozen=True)
class Session:
    id: str
    directory: Path
    events: EventLog


class SessionStore:
    def __init__(self, root: Path):
        self.root = (root / "sessions").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, on_event: Callable[[dict[str, Any]], None] | None = None) -> Session:
        session_id = uuid.uuid4().hex
        directory = self.root / session_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "session.json").write_text(
            json.dumps(
                {"id": session_id, "createdAt": datetime.now(timezone.utc).isoformat()},
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        return Session(session_id, directory, EventLog(directory / "events.jsonl", on_event))

    def path(self, session_id: str) -> Path:
        directory = (self.root / session_id).resolve()
        if directory.parent != self.root or not (directory / "session.json").is_file():
            raise FileNotFoundError(session_id)
        return directory

    def open(self, session_id: str, on_event: Callable[[dict[str, Any]], None] | None = None) -> Session:
        directory = self.path(session_id)
        return Session(session_id, directory, EventLog(directory / "events.jsonl", on_event))

    def delete(self, session_id: str) -> None:
        shutil.rmtree(self.path(session_id))


def create(
    root: Path,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> Session:
    return SessionStore(root).create(on_event)

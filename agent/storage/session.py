import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from filelock import FileLock

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

    def create(self, on_event: Callable[[dict[str, Any]], None] | None = None, **metadata: Any) -> Session:
        session_id = uuid.uuid4().hex
        directory = self.root / session_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "session.json").write_text(
            json.dumps(
                {**metadata, "id": session_id, "createdAt": datetime.now(timezone.utc).isoformat()},
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

    def metadata(self, session_id: str) -> dict:
        return json.loads((self.path(session_id) / "session.json").read_text(encoding="utf-8"))

    def summary(self, session_id: str) -> dict:
        """Cache list metadata; read only appended complete events when the log grows."""
        directory = self.path(session_id)
        meta_path, log_path = directory / "session.json", directory / "events.jsonl"
        cache_path = directory / "summary.json"
        with FileLock(str(directory / "summary.lock")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            stat = log_path.stat() if log_path.exists() else None
            source = [stat.st_ino, stat.st_size, stat.st_mtime_ns] if stat else [0, 0, 0]
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, ValueError):
                cached = {}
            if cached.get("source") != source:
                old = cached.get("source", [None, 0, 0])
                if old[0] != source[0] or source[1] <= old[1]:
                    cached = {}
                cached = cached or {"offset": 0, "title": "新会话", "empty": True,
                                    "status": "idle", "updatedAt": None}
                if stat:
                    with log_path.open("rb") as file:
                        file.seek(cached["offset"])
                        while file.tell() < source[1]:
                            line = file.readline(source[1] - file.tell())
                            if not line.endswith(b"\n"):
                                break
                            event = json.loads(line)
                            if event["type"] == "turn.started" and cached["empty"]:
                                cached["empty"] = False
                                cached["title"] = (" ".join(event.get("prompt", "").split())[:40]
                                                   or ("图片对话" if event.get("images") else "新会话"))
                            status = {"report.submitted": "submitted", "turn.failed": "failed",
                                      "turn.cancelled": "cancelled"}.get(event["type"])
                            if status:
                                cached["status"] = status
                            cached["updatedAt"] = event["time"] / 1e9
                            cached["offset"] = file.tell()
                cached["source"] = source
                temporary = cache_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(cached, ensure_ascii=False) + "\n", encoding="utf-8")
                temporary.replace(cache_path)
            return {
                "id": session_id, "parent_session_id": meta.get("parent_session_id"),
                "title": meta.get("title") or cached["title"], "empty": cached["empty"],
                "status": cached["status"], "createdAt": meta.get("createdAt"),
                "updatedAt": cached["updatedAt"] or meta_path.stat().st_mtime,
            }

    def children(self, session_id: str) -> list[str]:
        return [path.parent.name for path in self.root.glob("*/session.json")
                if json.loads(path.read_text(encoding="utf-8")).get("parent_session_id") == session_id]

    def delete(self, session_id: str) -> None:
        shutil.rmtree(self.path(session_id))

    def rename(self, session_id: str, title: str) -> str:
        title = title.strip()
        if not title or len(title) > 80 or any(ord(char) < 32 or ord(char) == 127 for char in title):
            raise ValueError("会话名称需要 1–80 个字符，不能包含换行或控制字符")
        path = self.path(session_id) / "session.json"
        with FileLock(str(path.with_suffix(".lock"))):
            meta = json.loads(path.read_text(encoding="utf-8"))
            meta["title"] = title
            temporary = path.with_suffix(".tmp")
            try:
                temporary.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        return title


def create(
    root: Path,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> Session:
    return SessionStore(root).create(on_event)

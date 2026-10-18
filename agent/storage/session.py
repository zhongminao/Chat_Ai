"""Session metadata lives in SQLite; session directories hold image and report files."""
import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .database import Database
from .event_log import EventLog
from .images import ImageStore


@dataclass(frozen=True)
class Session:
    id: str
    directory: Path
    events: EventLog
    images: ImageStore


class SessionStore:
    def __init__(self, root: Path):
        root = root.resolve()
        self.root = root / 'sessions'
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = Database(root / 'chat_ai.sqlite3')

    def create(self, on_event: Callable[[dict[str, Any]], None] | None = None, **metadata: Any) -> Session:
        session_id = uuid.uuid4().hex
        created = datetime.now(timezone.utc)
        parent, title = metadata.pop('parent_session_id', None), metadata.pop('title', None)
        payload = json.dumps(metadata, ensure_ascii=False)
        directory = self.root / session_id
        directory.mkdir()
        try:
            with self.database.connect(write=True) as connection:
                connection.execute('''INSERT INTO sessions (id, parent_session_id, created_at, updated_at, title, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)''', (session_id, parent, created.isoformat(), created.timestamp(), title, payload))
        except BaseException:
            directory.rmdir()
            raise
        return self.open(session_id, on_event)

    def path(self, session_id: str) -> Path:
        directory = (self.root / session_id).resolve()
        if directory.parent != self.root:
            raise FileNotFoundError(session_id)
        with self.database.connect() as connection:
            if connection.execute('SELECT 1 FROM sessions WHERE id=?', (session_id,)).fetchone() is None:
                raise FileNotFoundError(session_id)
        return directory

    def open(self, session_id: str, on_event: Callable[[dict[str, Any]], None] | None = None) -> Session:
        directory = self.path(session_id)
        return Session(session_id, directory, EventLog(self.database, session_id, on_event),
                       ImageStore(self.database, session_id, directory))

    def metadata(self, session_id: str) -> dict:
        with self.database.connect() as connection:
            row = connection.execute('SELECT * FROM sessions WHERE id=?', (session_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(session_id)
        result = {**json.loads(row['metadata']), 'id': row['id'], 'createdAt': row['created_at']}
        if row['parent_session_id'] is not None:
            result['parent_session_id'] = row['parent_session_id']
        if row['title'] is not None:
            result['title'] = row['title']
        return result

    def list_summaries(self) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute('''SELECT id, parent_session_id, COALESCE(NULLIF(title, ''), auto_title) AS title,
                empty, status, created_at AS createdAt, updated_at AS updatedAt FROM sessions ORDER BY updated_at DESC''').fetchall()
        return [{**dict(row), 'empty': bool(row['empty'])} for row in rows]

    def children(self, session_id: str) -> list[str]:
        with self.database.connect() as connection:
            return [row['id'] for row in connection.execute('SELECT id FROM sessions WHERE parent_session_id=?', (session_id,))]

    def delete(self, session_id: str) -> None:
        directory = self.path(session_id)
        with self.database.connect(write=True) as connection:
            connection.execute('DELETE FROM sessions WHERE id=?', (session_id,))
        shutil.rmtree(directory, ignore_errors=False)

    def rename(self, session_id: str, title: str) -> str:
        title = title.strip()
        if not title or len(title) > 80 or any(ord(char) < 32 or ord(char) == 127 for char in title):
            raise ValueError('会话名称需要 1–80 个字符，不能包含换行或控制字符')
        with self.database.connect(write=True) as connection:
            if not connection.execute('UPDATE sessions SET title=? WHERE id=?', (title, session_id)).rowcount:
                raise FileNotFoundError(session_id)
        return title

    def read_monitor(self, session_id: str) -> dict:
        with self.database.connect() as connection:
            row = connection.execute('SELECT cursor, resources FROM monitors WHERE session_id=?', (session_id,)).fetchone()
        return {'cursor': row['cursor'], 'resources': json.loads(row['resources'])} if row else {}

    def save_monitor(self, session_id: str, cursor: int, resources: dict) -> None:
        payload = json.dumps(resources, ensure_ascii=False)
        with self.database.connect(write=True) as connection:
            connection.execute('''INSERT INTO monitors VALUES (?, ?, ?) ON CONFLICT(session_id)
                DO UPDATE SET cursor=excluded.cursor, resources=excluded.resources''', (session_id, cursor, payload))

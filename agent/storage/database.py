"""SQLite connections and transactions shared by the storage modules."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    parent_session_id TEXT REFERENCES sessions(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at REAL NOT NULL,
    title TEXT,
    auto_title TEXT NOT NULL DEFAULT '新会话',
    empty INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'idle',
    event_seq INTEGER NOT NULL DEFAULT 0,
    image_seq INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_parent ON sessions(parent_session_id);
CREATE INDEX IF NOT EXISTS sessions_updated ON sessions(updated_at DESC);
CREATE TABLE IF NOT EXISTS events (
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    time INTEGER NOT NULL,
    type TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);
CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    name TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    size INTEGER NOT NULL,
    extension TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    UNIQUE (session_id, ordinal)
);
CREATE TABLE IF NOT EXISTS agent_to_agent_messages (
    id TEXT PRIMARY KEY,
    sender_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_to_agent_message_deliveries (
    message_id TEXT NOT NULL REFERENCES agent_to_agent_messages(id) ON DELETE CASCADE,
    recipient_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('to', 'cc')),
    read_at TEXT,
    PRIMARY KEY (message_id, recipient_id)
);
CREATE INDEX IF NOT EXISTS agent_to_agent_deliveries_inbox
    ON agent_to_agent_message_deliveries(recipient_id, read_at, message_id);
CREATE TABLE IF NOT EXISTS monitors (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    cursor INTEGER NOT NULL,
    resources TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        if sqlite3.sqlite_version_info < (3, 51, 3):
            raise RuntimeError(f'SQLite 3.51.3+ is required for WAL; found {sqlite3.sqlite_version}. '
                               'Upgrade SQLite in the Python environment before starting chat_ai.')
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        connection = self._connection = sqlite3.connect(
            self.path, timeout=5, isolation_level=None, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA synchronous=NORMAL')
            connection.executescript(SCHEMA)
        except BaseException:
            connection.close()
            raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def connect(self, *, write: bool = False, durable: bool = True):
        with self._lock:
            connection = self._connection
            try:
                if write:
                    connection.execute('PRAGMA synchronous=' + ('FULL' if durable else 'NORMAL'))
                    connection.execute('BEGIN IMMEDIATE')
                yield connection
                if write:
                    connection.commit()
            except BaseException:
                connection.rollback()
                raise

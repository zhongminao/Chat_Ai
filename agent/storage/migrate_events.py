"""Offline SQLite events -> per-session JSONL migration.

STOP ALL chat_ai processes/writers, back up storage, then run this module on the
storage directory. Never run against a live installation: a SQLite snapshot
protects reads, but cannot protect JSONL files from concurrent writers.
The SQLite database is not changed or deleted. Rerunning is safe only when
existing journals match the database snapshot byte-for-byte.
"""
import argparse
import json
import os
import sqlite3
import stat
import tempfile
from urllib.parse import quote
from pathlib import Path


def _regular_file(path: Path) -> None:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f'Not a regular file: {path}')


def _lines(db: sqlite3.Connection, session_id: str, expected: int):
    if type(expected) is not int or expected < 0:
        raise ValueError(f'Invalid event_seq: {session_id}')
    count = 0
    cursor = db.execute('SELECT seq, time, type, data FROM events WHERE session_id=? ORDER BY seq', (session_id,))
    for seq, timestamp, kind, payload in cursor:
        count += 1
        if type(seq) is not int or seq != count or type(timestamp) is not int or type(kind) is not str or not kind:
            raise ValueError(f'Invalid SQLite event sequence/type/time: {session_id}/{count}')
        if type(payload) is not str:
            raise ValueError(f'Invalid event payload: {session_id}/{seq}')
        try:
            data = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise ValueError(f'Invalid event payload: {session_id}/{seq}') from exc
        if not isinstance(data, dict) or {'seq', 'time', 'type'} & data.keys():
            raise ValueError(f'Invalid event payload: {session_id}/{seq}')
        # Preserve the entire payload, including context.compacted messages.
        yield (json.dumps({'seq': seq, 'time': timestamp, 'type': kind, **data}, ensure_ascii=False)
               + '\n').encode('utf-8')
    if count != expected:
        raise ValueError(f'Invalid SQLite event sequence/count: {session_id}: {count} != {expected}')


def _matches(path: Path, generated: Path) -> bool:
    _regular_file(path)
    with path.open('rb') as old, generated.open('rb') as new:
        while True:
            a, b = old.read(1024 * 1024), new.read(1024 * 1024)
            if a != b:
                return False
            if not a:
                return True


def migrate(root: Path) -> None:
    """Migrate a stopped installation; validate against one SQLite read snapshot.

    Existing nonmatching journals are never overwritten. Each session is
    published atomically; a failed multi-session run may leave earlier sessions
    migrated and can be resumed after the problem is fixed.
    """
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    sessions_root = root / 'sessions'
    if sessions_root.is_symlink() or not sessions_root.is_dir():
        raise ValueError(f'Missing or unsafe sessions directory: {sessions_root}')
    db_path = root / 'chat_ai.sqlite3'
    if db_path.is_symlink():
        raise ValueError(f'Unsafe database symlink: {db_path}')
    _regular_file(db_path)  # Do not let sqlite3 create a new database.
    # URI mode=ro ensures no database creation; the read transaction includes
    # WAL commits and holds a single consistent snapshot across all sessions.
    with sqlite3.connect('file:' + quote(str(db_path)) + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        # BEGIN is deferred: the first SELECT fixes the snapshot before any
        # per-session file is published.
        db.execute('SELECT COUNT(*) FROM sessions').fetchone()
        sessions = db.execute('SELECT id, event_seq FROM sessions ORDER BY id')
        for session_id, expected in sessions:
            if (not isinstance(session_id, str) or not session_id or session_id in ('.', '..')
                    or '/' in session_id or '\\' in session_id or '\x00' in session_id):
                raise ValueError(f'Unsafe session id: {session_id!r}')
            directory = sessions_root / session_id
            if directory.is_symlink() or not directory.is_dir() or directory.resolve() != directory:
                raise ValueError(f'Missing or unsafe session directory: {directory}')
            target = directory / 'events.jsonl'
            # A unique temporary avoids clobbering a previous interrupted run.
            fd, name = tempfile.mkstemp(prefix='.events.jsonl.', suffix='.tmp', dir=directory)
            temporary = Path(name)
            try:
                with os.fdopen(fd, 'wb') as output:
                    for line in _lines(db, session_id, expected):
                        output.write(line)
                    output.flush()
                    os.fsync(output.fileno())
                if target.is_symlink():
                    raise FileExistsError(f'Unsafe journal symlink: {target}')
                if target.exists():
                    if not _matches(target, temporary):
                        raise FileExistsError(f'Non-matching journal, refuse overwrite: {target}')
                    continue
                # Exclusive link prevents replacing a journal created concurrently.
                # On the same filesystem this is atomic. The temporary is unlinked
                # after publication; sync directory metadata for crash durability.
                try:
                    os.link(temporary, target)
                except FileExistsError:
                    if target.is_symlink() or not _matches(target, temporary):
                        raise FileExistsError(f'Non-matching journal, refuse overwrite: {target}') from None
                    continue
                dir_fd = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            finally:
                temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='OFFLINE ONLY: stop ALL writers and back up storage before migrating')
    parser.add_argument('storage', type=Path)
    migrate(parser.parse_args().storage)

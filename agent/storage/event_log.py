"""Per-session append-only JSONL journal; SQLite stores a repairable listing summary.

The journal is authoritative. Migration/replacement of a journal is strictly offline.
"""
import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from .database import Database


class EventLog:
    def __init__(self, database: Database, session_id: str, directory: Path,
                 on_append: Callable[[dict[str, Any]], None] | None = None, *, index: dict | None = None):
        self.database = database
        self.session_id = session_id
        self.path = directory / 'events.jsonl'
        self.on_append = on_append
        self._known_inode: tuple[int, int] | None = None
        self._index = index if index is not None else {}
        self._lock = self._index.setdefault('lock', RLock())

    @contextmanager
    def _locked(self, exclusive: bool = False):
        # flock coordinates different handles, threads and processes on the same inode.
        with self._lock, self.path.open('r+b' if exclusive else 'rb') as file:
            fcntl.flock(file, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                # Never write into a journal inode replaced by an offline migration.
                identity = (os.fstat(file.fileno()).st_dev, os.fstat(file.fileno()).st_ino)
                current = self.path.stat()
                if identity != (current.st_dev, current.st_ino):
                    raise RuntimeError(f'Event journal replaced while active: {self.path}')
                if self._known_inode is not None and identity != self._known_inode:
                    raise RuntimeError(f'Event journal replaced while active: {self.path}')
                self._known_inode = identity
                yield file
            finally:
                fcntl.flock(file, fcntl.LOCK_UN)

    def _missing(self):
        raise FileNotFoundError(f'No event journal: {self.path}; restore the session from a JSONL backup')

    @staticmethod
    def _signature(file):
        value = os.fstat(file.fileno())
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns

    @staticmethod
    def _validate(line: bytes, expected: int, path: Path, offset: int) -> dict[str, Any]:
        try:
            record = json.loads(line)
            if (not isinstance(record, dict) or type(record.get('seq')) is not int
                    or record['seq'] != expected or type(record.get('time')) is not int
                    or not isinstance(record.get('type'), str) or not record['type']):
                raise ValueError('invalid event or sequence')
        except (UnicodeError, ValueError, TypeError) as exc:
            raise ValueError(f'Corrupt event journal {path} at byte {offset}') from exc
        return record

    def _iter(self, file, *, repair: bool = False, after: int = 0):
        # Shared by this store's handles, under flock. Foreign writes invalidate
        # the index; checkpoints only skip a prefix already validated unchanged.
        offsets = self._index['offsets'] if self._index.get('signature') == self._signature(file) else [0]
        block = min(max(after, 0) // 256, len(offsets) - 1)
        self._index['signature'] = None
        file.seek(offsets[block])
        expected = block * 256 + 1
        while True:
            start = file.tell()
            line = file.readline()
            if not line:
                break
            try:
                record = self._validate(line, expected, self.path, start)
            except ValueError:
                if line.endswith(b'\n'):
                    raise
                try:
                    json.loads(line)
                except (UnicodeError, ValueError):
                    if not repair:
                        return  # An incomplete crash tail is not a reusable index.
                    file.truncate(start)
                    file.flush()
                    os.fsync(file.fileno())
                    break
                raise
            if not line.endswith(b'\n'):
                if not repair:
                    if record['seq'] > after:
                        yield record
                    return
                file.write(b'\n')
                file.flush()
                os.fsync(file.fileno())
            if expected % 256 == 0 and len(offsets) <= expected // 256:
                offsets.append(file.tell())
            expected += 1
            if record['seq'] > after:
                yield record
        self._index.update(offsets=offsets, seq=expected - 1, signature=self._signature(file))

    @staticmethod
    def _projection(connection, session_id: str, records) -> None:
        row = connection.execute('SELECT event_seq, activity_seq, status FROM sessions WHERE id=?',
                                 (session_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(session_id)
        seq = row['event_seq']
        activity_seq, status = row['activity_seq'], row['status']
        title = timestamp = None
        for record in records:
            if record['seq'] <= seq:
                continue
            if record['seq'] != seq + 1:
                raise ValueError(f'Non-contiguous event projection: {session_id}')
            event_type = record['type']
            if event_type == 'turn.started' and title is None:
                title = ' '.join(record.get('prompt', '').split())[:40] or ('图片对话' if record.get('images') else '新会话')
            if event_type == 'turn.completed':
                # Report submission is followed by completion in the same turn.
                status = 'submitted' if status == 'submitted' else 'idle'
            else:
                status = {'turn.started': 'running', 'report.submitted': 'submitted',
                          'turn.failed': 'failed', 'turn.cancelled': 'cancelled'}.get(event_type, status)
            # A journal cursor, not an event count: user edits, model changes,
            # uploads and internal/tool events must not trigger unread badges.
            if event_type in {'message.delta', 'report.submitted', 'turn.completed',
                              'turn.failed', 'turn.cancelled'}:
                activity_seq = record['seq']
            timestamp = record['time'] / 1e9
            seq += 1
        if timestamp is not None:
            connection.execute('''UPDATE sessions SET event_seq=?, updated_at=?,
                auto_title=CASE WHEN empty=1 THEN COALESCE(?, auto_title) ELSE auto_title END,
                empty=CASE WHEN ? IS NOT NULL THEN 0 ELSE empty END,
                status=?, activity_seq=? WHERE id=?''',
                               (seq, timestamp, title, title, status, activity_seq, session_id))

    def repair_summary(self) -> None:
        try:
            with self._locked(exclusive=True) as file:
                self.repair_summary_locked(file)
        except FileNotFoundError:
            self._missing()

    def append(self, event_type: str, *, durable: bool = True, **data: Any) -> dict[str, Any]:
        if {'seq', 'time', 'type'} & data.keys():
            raise ValueError('Event sequence, time and type are assigned by EventLog')
        # Serialize before opening; a bad payload cannot consume a sequence.
        json.dumps(data, ensure_ascii=False)
        try:
            with self._locked(exclusive=True) as file:
                if self._index.get('signature') != self._signature(file):
                    for _ in self._iter(file, repair=True):
                        pass
                seq = self._index['seq']
                with self.database.connect() as db:
                    row = db.execute('SELECT event_seq FROM sessions WHERE id=?', (self.session_id,)).fetchone()
                if row is None:
                    raise FileNotFoundError(self.session_id)
                if row['event_seq'] > seq:
                    raise ValueError(f'SQLite summary ahead of event journal: {self.session_id}')
                # Project the outstanding suffix only on a durable boundary.
                if durable and row['event_seq'] < seq:
                    self.repair_summary_locked(file, row['event_seq'])
                record = {'seq': seq + 1, 'time': time.time_ns(), 'type': event_type, **data}
                line = (json.dumps(record, ensure_ascii=False) + '\n').encode('utf-8')
                file.seek(0, os.SEEK_END)
                offset = file.tell()
                try:
                    written = file.write(line)
                    if written != len(line):
                        raise OSError('Incomplete journal write')
                    file.flush()
                except OSError:
                    # Never follow a partial line with another event. A later
                    # append/repair will truncate the incomplete crash tail.
                    self._index['signature'] = None
                    raise
                if len(self._index['offsets']) <= seq // 256:
                    self._index['offsets'].append(offset)
                self._index.update(seq=record['seq'], signature=self._signature(file))
                if durable:
                    os.fsync(file.fileno())
                # A durable boundary makes prior deltas and the boundary visible in SQLite.
                if durable:
                    with self.database.connect(write=True) as db:
                        self._projection(db, self.session_id, [record])
            # Do not hold an exclusive flock while publishing: observers may read.
            if self.on_append:
                self.on_append(record)
            return record
        except FileNotFoundError:
            self._missing()

    def repair_summary_locked(self, file, projected: int | None = None) -> None:
        if projected is None:
            with self.database.connect() as db:
                row = db.execute('SELECT event_seq FROM sessions WHERE id=?', (self.session_id,)).fetchone()
            if row is None:
                raise FileNotFoundError(self.session_id)
            projected = row['event_seq']
        records = list(self._iter(file, repair=True, after=projected))
        if self._index['seq'] < projected:
            raise ValueError(f'SQLite summary ahead of event journal: {self.session_id}')
        if records:
            with self.database.connect(write=True) as db:
                self._projection(db, self.session_id, records)

    def read(self, after: int = 0) -> list[dict[str, Any]]:
        try:
            with self._locked() as file:
                return list(self._iter(file, after=after))
        except FileNotFoundError:
            self._missing()

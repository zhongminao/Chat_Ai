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
                 on_append: Callable[[dict[str, Any]], None] | None = None):
        self.database = database
        self.session_id = session_id
        self.path = directory / 'events.jsonl'
        self.on_append = on_append
        self._lock = RLock()
        self._known_seq: int | None = None
        self._known_inode: tuple[int, int] | None = None
        self._known_size: int | None = None

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
        raise FileNotFoundError(f'No event journal: {self.path}; migrate SQLite events offline before starting')

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

    def _tail(self, file, *, repair: bool = False) -> tuple[int, int]:
        """Validate the last line in O(size of last line); full validation is for reads/repair.

        A completed JSON record without newline is completed rather than discarded. A
        truncated final record is discarded only during exclusive recovery.
        """
        file.seek(0, os.SEEK_END)
        end = file.tell()
        if not end:
            return 0, 0
        pos = end - 1
        file.seek(pos)
        terminated = file.read(1) == b'\n'
        if terminated:
            pos -= 1
        while pos >= 0:
            file.seek(pos)
            if file.read(1) == b'\n':
                break
            pos -= 1
        start = pos + 1
        file.seek(start)
        line = file.read(end - start)
        if not terminated:
            try:
                record = json.loads(line)
            except (UnicodeError, ValueError):
                if not repair:
                    return 0, start  # ignore an incomplete concurrent/crash tail
                file.truncate(start)
                file.flush()
                os.fsync(file.fileno())
                self._known_seq = None
                self._known_size = None
                return self._tail(file, repair=True)
            if (not isinstance(record, dict) or type(record.get('seq')) is not int
                    or type(record.get('time')) is not int
                    or not isinstance(record.get('type'), str) or not record['type']):
                raise ValueError(f'Corrupt event journal {self.path} at byte {start}')
            if repair:
                file.seek(0, os.SEEK_END)
                file.write(b'\n')
                file.flush()
                os.fsync(file.fileno())
                self._known_seq = None
                self._known_size = None
            return record['seq'], record['time']
        try:
            raw = json.loads(line)
            expected = raw.get('seq') if isinstance(raw, dict) else -1
        except (UnicodeError, ValueError) as exc:
            raise ValueError(f'Corrupt event journal {self.path} at byte {start}') from exc
        record = self._validate(line, expected, self.path, start)
        return record['seq'], record['time']

    def _iter(self, file, *, repair: bool = False):
        file.seek(0)
        expected = 1
        while True:
            start = file.tell()
            line = file.readline()
            if not line:
                return
            if not line.endswith(b'\n'):
                try:
                    record = self._validate(line, expected, self.path, start)
                except ValueError:
                    # Only an incomplete final line can be safely discarded.
                    try:
                        json.loads(line)
                    except (UnicodeError, ValueError):
                        if repair:
                            file.truncate(start)
                            file.flush()
                            os.fsync(file.fileno())
                        return
                    raise
                if repair:
                    file.seek(0, os.SEEK_END)
                    file.write(b'\n')
                    file.flush()
                    os.fsync(file.fileno())
                yield record
                return
            yield self._validate(line, expected, self.path, start)
            expected += 1

    @staticmethod
    def _projection(connection, session_id: str, records) -> None:
        row = connection.execute('SELECT event_seq FROM sessions WHERE id=?', (session_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(session_id)
        seq = row['event_seq']
        for record in records:
            if record['seq'] <= seq:
                continue
            if record['seq'] != seq + 1:
                raise ValueError(f'Non-contiguous event projection: {session_id}')
            event_type = record['type']
            title = (' '.join(record.get('prompt', '').split())[:40]
                     or ('图片对话' if record.get('images') else '新会话')) if event_type == 'turn.started' else ''
            status = {'report.submitted': 'submitted', 'turn.failed': 'failed',
                      'turn.cancelled': 'cancelled'}.get(event_type)
            connection.execute('''UPDATE sessions SET event_seq=?, updated_at=?,
                auto_title=CASE WHEN ?='turn.started' AND empty=1 THEN ? ELSE auto_title END,
                empty=CASE WHEN ?='turn.started' THEN 0 ELSE empty END,
                status=COALESCE(?, status) WHERE id=?''',
                (record['seq'], record['time'] / 1e9, event_type, title, event_type, status, session_id))
            seq += 1

    def repair_summary(self) -> None:
        try:
            with self._locked(exclusive=True) as file:
                # Validate entire file before changing the projection; repair only crash tail.
                records = list(self._iter(file, repair=True))
                with self.database.connect() as db:
                    row = db.execute('SELECT event_seq FROM sessions WHERE id=?', (self.session_id,)).fetchone()
                if row is None:
                    raise FileNotFoundError(self.session_id)
                if row['event_seq'] > len(records):
                    raise ValueError(f'SQLite summary ahead of event journal: {self.session_id}')
                if row['event_seq'] < len(records):
                    with self.database.connect(write=True) as db:
                        self._projection(db, self.session_id, records[row['event_seq']:])
        except FileNotFoundError:
            self._missing()

    def append(self, event_type: str, *, durable: bool = True, **data: Any) -> dict[str, Any]:
        if {'seq', 'time', 'type'} & data.keys():
            raise ValueError('Event sequence, time and type are assigned by EventLog')
        # Serialize before opening; a bad payload cannot consume a sequence.
        json.dumps(data, ensure_ascii=False)
        try:
            with self._locked(exclusive=True) as file:
                seq, _ = self._tail(file, repair=True)
                if self._known_seq is None or seq != self._known_seq or (
                        self._known_size is not None and file.seek(0, os.SEEK_END) != self._known_size):
                    # First access / foreign writer / crash recovery: validate full chain.
                    seq = self._check_sequence(file)
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
                try:
                    written = file.write(line)
                    if written != len(line):
                        raise OSError('Incomplete journal write')
                    file.flush()
                except OSError:
                    # Never follow a partial line with another event. A later
                    # append/repair will truncate the incomplete crash tail.
                    self._known_seq = None
                    raise
                self._known_seq = record['seq']
                self._known_size = file.tell()
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

    def _check_sequence(self, file) -> int:
        count = 0
        for record in self._iter(file, repair=True):
            count = record['seq']
        return count

    def repair_summary_locked(self, file, projected: int) -> None:
        records = list(self._iter(file, repair=True))
        if len(records) < projected:
            raise ValueError(f'SQLite summary ahead of event journal: {self.session_id}')
        if len(records) > projected:
            with self.database.connect(write=True) as db:
                self._projection(db, self.session_id, records[projected:])

    def read(self, after: int = 0) -> list[dict[str, Any]]:
        try:
            with self._locked() as file:
                return [record for record in self._iter(file) if record['seq'] > after]
        except FileNotFoundError:
            self._missing()

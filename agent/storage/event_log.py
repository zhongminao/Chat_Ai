"""Ordered session events; publish only after the transaction commits."""
import json
import time
from threading import RLock
from typing import Any, Callable

from .database import Database


class EventLog:
    def __init__(self, database: Database, session_id: str,
                 on_append: Callable[[dict[str, Any]], None] | None = None):
        self.database = database
        self.session_id = session_id
        self.on_append = on_append
        self._lock = RLock()

    def append(self, event_type: str, *, durable: bool = True, **data: Any) -> dict[str, Any]:
        if {'seq', 'time', 'type'} & data.keys():
            raise ValueError('Event sequence, time and type are assigned by EventLog')
        payload = json.dumps(data, ensure_ascii=False)
        with self._lock:
            with self.database.connect(write=True, durable=durable) as connection:
                row = connection.execute('SELECT event_seq FROM sessions WHERE id=?', (self.session_id,)).fetchone()
                if row is None:
                    raise FileNotFoundError(self.session_id)
                sequence, timestamp = row['event_seq'] + 1, time.time_ns()
                record = {'seq': sequence, 'time': timestamp, 'type': event_type, **data}
                connection.execute('INSERT INTO events VALUES (?, ?, ?, ?, ?)',
                                   (self.session_id, sequence, timestamp, event_type, payload))
                title = (' '.join(data.get('prompt', '').split())[:40]
                         or ('图片对话' if data.get('images') else '新会话')) if event_type == 'turn.started' else ''
                status = {'report.submitted': 'submitted', 'turn.failed': 'failed',
                          'turn.cancelled': 'cancelled'}.get(event_type)
                connection.execute('''UPDATE sessions SET event_seq=?, updated_at=?,
                    auto_title=CASE WHEN ?='turn.started' AND empty=1 THEN ? ELSE auto_title END,
                    empty=CASE WHEN ?='turn.started' THEN 0 ELSE empty END,
                    status=COALESCE(?, status) WHERE id=?''',
                    (sequence, timestamp / 1e9, event_type, title, event_type, status, self.session_id))
            if self.on_append:
                self.on_append(record)
            return record

    def read(self, after: int = 0) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute('SELECT seq, time, type, data FROM events WHERE session_id=? AND seq>? ORDER BY seq',
                                      (self.session_id, after)).fetchall()
        return [{'seq': row['seq'], 'time': row['time'], 'type': row['type'], **json.loads(row['data'])} for row in rows]

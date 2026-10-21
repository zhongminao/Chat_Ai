"""Private, transactional agent-to-agent deliveries, separate from conversation events."""
import uuid
from datetime import datetime, timezone

from .database import Database


def _now():
    return datetime.now(timezone.utc).isoformat()


class AgentToAgentMailbox:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _root(connection, session_id: str) -> str:
        row = connection.execute('SELECT parent_session_id FROM sessions WHERE id=?', (session_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(session_id)
        return row['parent_session_id'] or session_id

    def send(self, sender_id: str, recipient_id: str, content: str, *, cc=(), kind='notification') -> dict:
        if not isinstance(content, str) or not content.strip():
            raise ValueError('content must be non-empty text')
        if kind not in {'notification', 'feedback'}:
            raise ValueError('kind must be notification or feedback')
        if not isinstance(recipient_id, str) or not recipient_id:
            raise ValueError('recipient must be a session ID')
        if not isinstance(cc, (list, tuple)) or not all(isinstance(item, str) for item in cc):
            raise ValueError('cc must be a sequence of session IDs')
        cc = tuple(cc)
        if len(cc) != len(set(cc)) or recipient_id in cc:
            raise ValueError('duplicate recipients')
        recipients = [{'session_id': recipient_id, 'role': 'to'},
                      *({'session_id': item, 'role': 'cc'} for item in cc)]
        message_id = uuid.uuid4().hex
        with self.database.connect(write=True) as connection:
            root = self._root(connection, sender_id)
            sender_is_child = root != sender_id
            if (sender_is_child and kind != 'feedback') or (not sender_is_child and kind != 'notification'):
                raise ValueError('kind does not match sender role')
            if sender_id == recipient_id or sender_id in cc:
                raise PermissionError('cannot send to yourself')
            for recipient in recipients:
                target = recipient['session_id']
                if self._root(connection, target) != root:
                    raise PermissionError('recipient is outside the task tree')
                if sender_is_child and recipient['role'] == 'to' and target != root:
                    raise PermissionError('child must address the parent')
                if recipient['role'] == 'cc' and target == root:
                    raise PermissionError('parent must be the primary recipient')
            connection.execute('INSERT INTO agent_to_agent_messages VALUES (?, ?, ?, ?, ?)',
                               (message_id, sender_id, content, kind, _now()))
            connection.executemany('INSERT INTO agent_to_agent_message_deliveries VALUES (?, ?, ?, NULL)',
                                   [(message_id, r['session_id'], r['role']) for r in recipients])
        return {'id': message_id, 'recipients': recipients}

    def list(self, session_id: str, unread_only: bool = False) -> list[dict]:
        with self.database.connect() as connection:
            self._root(connection, session_id)
            rows = connection.execute('''SELECT m.id, m.sender_id, m.content, m.kind, m.created_at,
                d.role, d.read_at FROM agent_to_agent_message_deliveries AS d
                JOIN agent_to_agent_messages AS m ON m.id=d.message_id
                WHERE d.recipient_id=? AND (?=0 OR d.read_at IS NULL)
                ORDER BY m.created_at DESC, m.id DESC''', (session_id, int(bool(unread_only)))).fetchall()
            return [dict(row) for row in rows]

    def read(self, session_id: str, message_id: str) -> dict:
        with self.database.connect(write=True) as connection:
            self._root(connection, session_id)
            row = connection.execute('''SELECT m.id, m.sender_id, m.content, m.kind, m.created_at,
                d.role, d.read_at FROM agent_to_agent_message_deliveries AS d
                JOIN agent_to_agent_messages AS m ON m.id=d.message_id
                WHERE d.recipient_id=? AND m.id=?''', (session_id, message_id)).fetchone()
            if row is None:
                raise FileNotFoundError(message_id)
            if row['read_at'] is None:
                timestamp = _now()
                connection.execute('''UPDATE agent_to_agent_message_deliveries SET read_at=?
                    WHERE recipient_id=? AND message_id=? AND read_at IS NULL''',
                                   (timestamp, session_id, message_id))
                return {**dict(row), 'read_at': timestamp}
            return dict(row)

    def unread_count(self, session_id: str) -> int:
        with self.database.connect() as connection:
            self._root(connection, session_id)
            return connection.execute('''SELECT COUNT(*) FROM agent_to_agent_message_deliveries
                WHERE recipient_id=? AND read_at IS NULL''', (session_id,)).fetchone()[0]

    def latest_id(self, session_id: str) -> str | None:
        with self.database.connect() as connection:
            self._root(connection, session_id)
            row = connection.execute('''SELECT d.message_id FROM agent_to_agent_message_deliveries d
                JOIN agent_to_agent_messages m ON m.id=d.message_id WHERE d.recipient_id=?
                ORDER BY m.created_at DESC, m.id DESC LIMIT 1''', (session_id,)).fetchone()
            return row[0] if row else None

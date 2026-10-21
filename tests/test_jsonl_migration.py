"""Offline migration tests use only isolated temporary SQLite databases."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.storage.migrate_events import migrate


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'sessions').mkdir()
        self.db = sqlite3.connect(self.root / 'chat_ai.sqlite3')
        self.addCleanup(self.db.close)
        self.db.executescript('CREATE TABLE sessions(id TEXT, event_seq INTEGER);'
                              'CREATE TABLE events(session_id TEXT, seq INTEGER, time INTEGER, type TEXT, data TEXT);')

    def session(self, name='abc', rows=(), expected=None):
        (self.root / 'sessions' / name).mkdir()
        self.db.execute('INSERT INTO sessions VALUES (?, ?)', (name, len(rows) if expected is None else expected))
        self.db.executemany('INSERT INTO events VALUES (?, ?, ?, ?, ?)',
                            [(name, *row) for row in rows])
        self.db.commit()
        return self.root / 'sessions' / name / 'events.jsonl'

    def test_compaction_and_unicode_full_payload_idempotence(self):
        payload = {'messages': [{'role': 'assistant', 'content': '摘要', 'nested': [1, None]}], 'extra': {'a': True}}
        target = self.session(rows=[(1, 123, 'context.compacted', json.dumps(payload)),
                                    (2, 124, 'turn.completed', '{}')])
        migrate(self.root)
        records = [json.loads(line) for line in target.read_text().splitlines()]
        self.assertEqual(records[0], {'seq': 1, 'time': 123, 'type': 'context.compacted', **payload})
        self.assertEqual(records[1]['seq'], 2)
        before = target.stat().st_ino
        migrate(self.root)
        self.assertEqual(target.stat().st_ino, before)
        self.assertEqual(list(target.parent.glob('*.tmp')), [])
        target.write_text('{}\n')
        with self.assertRaises(FileExistsError):
            migrate(self.root)
        self.assertEqual(target.read_text(), '{}\n')

    def test_invalid_rows_do_not_publish(self):
        invalid = [(2, 1, 'x', '{}'), (1, 'bad', 'x', '{}'), (1, 1, '', '{}'),
                   (1, 1, 'x', '[]'), (1, 1, 'x', '{oops'),
                   (1, 1, 'x', '{"seq":42}'), (1, 1, 'x', 'null')]
        for row in invalid:
            with self.subTest(row=row):
                self.db.execute('DELETE FROM events')
                self.db.execute('DELETE FROM sessions')
                path = self.root / 'sessions' / 'abc'
                path.mkdir(exist_ok=True)
                self.db.execute('INSERT INTO sessions VALUES (?, ?)', ('abc', 1))
                self.db.execute('INSERT INTO events VALUES (?, ?, ?, ?, ?)', ('abc', *row))
                self.db.commit()
                with self.assertRaises(ValueError):
                    migrate(self.root)
                self.assertFalse((path / 'events.jsonl').exists())
        self.db.execute('UPDATE sessions SET event_seq=2')
        self.db.execute('DELETE FROM events')
        self.db.commit()
        with self.assertRaises(ValueError):
            migrate(self.root)

    def test_empty_and_missing_or_unsafe_storage(self):
        target = self.session(rows=[])
        migrate(self.root)
        self.assertEqual(target.read_bytes(), b'')
        with self.assertRaises(FileNotFoundError):
            migrate(self.root / 'missing')
        with tempfile.TemporaryDirectory() as other:
            (Path(other) / "sessions").mkdir()
            with self.assertRaises(FileNotFoundError):
                migrate(Path(other))
        self.db.execute('INSERT INTO sessions VALUES (?, ?)', ('../escape', 0))
        self.db.commit()
        with self.assertRaises(ValueError):
            migrate(self.root)

    def test_reject_symlink_directory_and_journal(self):
        target = self.session()
        with tempfile.TemporaryDirectory() as other:
            (self.root / 'sessions' / 'abc').rmdir()
            (self.root / 'sessions' / 'abc').symlink_to(other, target_is_directory=True)
            with self.assertRaises(ValueError):
                migrate(self.root)
            (self.root / 'sessions' / 'abc').unlink()
            target.parent.mkdir()
            destination = Path(other) / 'journal'
            destination.write_text('untouched')
            target.symlink_to(destination)
            with self.assertRaises(FileExistsError):
                migrate(self.root)
            self.assertEqual(destination.read_text(), 'untouched')

    def test_snapshot_reads_wal_commits_and_streams_rows(self):
        self.db.execute('PRAGMA journal_mode=WAL')
        rows = [(i, i, 'message.delta', json.dumps({'text': str(i)})) for i in range(1, 1501)]
        target = self.session(rows=rows)
        with patch('agent.storage.migrate_events.os.fsync', wraps=__import__('os').fsync) as sync:
            migrate(self.root)
            self.assertGreaterEqual(sync.call_count, 2)
        self.assertEqual(len(target.read_bytes().splitlines()), len(rows))


if __name__ == '__main__':
    unittest.main()

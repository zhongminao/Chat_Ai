import sqlite3
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from agent.storage.session import SessionStore


class SessionListSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SessionStore(Path(self.temp.name))
        self.addCleanup(self.store.database.close)
        self.session = self.store.create()

    def summary(self):
        return next(item for item in self.store.list_summaries() if item['id'] == self.session.id)

    def test_persisted_summary_does_not_parse_event_bodies(self):
        self.session.events.append('turn.started', prompt='hello summary', images=[])
        self.session.events.append('report.submitted', content='# Large report body')
        initial = self.summary()
        self.assertEqual((initial['title'], initial['status'], initial['empty']), ('hello summary', 'submitted', False))
        self.assertEqual(initial['activitySeq'], 2)
        with patch('agent.storage.event_log.json.loads', side_effect=AssertionError('summary must not parse events')):
            self.assertEqual(self.store.list_summaries(), [initial])
        restored = SessionStore(Path(self.temp.name))
        self.addCleanup(restored.database.close)
        self.assertEqual(restored.list_summaries(), [initial])
        self.session.events.append('turn.failed', reason='later failure')
        updated = self.summary()
        self.assertEqual(updated['status'], 'failed')
        self.assertEqual(updated['title'], 'hello summary')
        self.assertGreater(updated['updatedAt'], initial['updatedAt'])

    def test_empty_images_rename_and_delete(self):
        self.assertTrue(self.summary()['empty'])
        self.assertEqual(self.summary()['title'], '新会话')
        self.session.events.append('model.changed', new={'name': 'test'})
        self.assertTrue(self.summary()['empty'])
        self.session.events.append('turn.started', prompt='', images=[{'id': 'image'}])
        self.assertEqual(self.summary()['title'], '图片对话')
        self.assertFalse(self.summary()['empty'])
        self.store.update(self.session.id, title='custom title')
        self.assertEqual(self.summary()['title'], 'custom title')
        self.store.delete(self.session.id)
        self.assertFalse(self.session.directory.exists())
        self.assertEqual(self.store.list_summaries(), [])

    def test_activity_cursor_ignores_user_edits_images_and_internal_events(self):
        self.assertEqual(self.summary()['activitySeq'], 0)
        log = self.session.events
        log.append('turn.started', prompt='hello')
        self.assertEqual((self.summary()['activitySeq'], self.summary()['status']), (0, 'running'))
        visible = log.append('message.delta', text='answer')
        self.assertEqual(self.summary()['activitySeq'], visible['seq'])
        self.store.update(self.session.id, title='renamed', pinned=True, archived=True)
        output = BytesIO()
        Image.new('RGB', (2, 2), 'blue').save(output, format='PNG')
        self.session.images.add(output.getvalue(), 'upload.png')
        self.assertEqual(self.summary()['activitySeq'], visible['seq'])
        for event_type in ('model.changed', 'model.started', 'model.completed', 'reasoning.delta',
                           'tool.requested', 'tool.completed', 'context.compacted', 'context.measured'):
            with self.subTest(event_type=event_type):
                log.append(event_type)
                self.assertEqual(self.summary()['activitySeq'], visible['seq'])
        with patch('agent.storage.event_log.EventLog.read', side_effect=AssertionError('no journal reads')), \
             patch('agent.storage.event_log.EventLog._iter', side_effect=AssertionError('no journal scans')):
            self.assertEqual(self.summary()['activitySeq'], visible['seq'])

    def test_latest_turn_status_and_visible_outcomes(self):
        log = self.session.events
        for terminal, expected in [('turn.failed', 'failed'), ('turn.cancelled', 'cancelled'),
                                   ('turn.completed', 'idle'), ('report.submitted', 'submitted')]:
            with self.subTest(terminal=terminal):
                before = self.summary()['activitySeq']
                log.append('turn.started', prompt='next')
                self.assertEqual((self.summary()['status'], self.summary()['activitySeq']), ('running', before))
                record = log.append(terminal)
                self.assertEqual((self.summary()['status'], self.summary()['activitySeq']),
                                 (expected, record['seq']))
        # Completion follows successful submission and must preserve it, even
        # across a restart; a subsequent turn resets it to running/idle.
        restored = SessionStore(Path(self.temp.name))
        self.addCleanup(restored.database.close)
        completed = restored.open(self.session.id).events.append('turn.completed')
        self.assertEqual((self.summary()['status'], self.summary()['activitySeq']), ('submitted', completed['seq']))
        log.append('turn.started', prompt='new turn')
        log.append('turn.completed')
        self.assertEqual(self.summary()['status'], 'idle')

    def test_stream_activity_projects_at_boundary_and_recovers_after_restart(self):
        log = self.session.events
        log.append('turn.started', prompt='stream')
        first = log.append('message.delta', durable=False, text='first')
        self.assertEqual(self.summary()['activitySeq'], 0)
        log.append('model.completed')
        self.assertEqual(self.summary()['activitySeq'], first['seq'])
        second = log.append('message.delta', durable=False, text='second')
        self.assertEqual(self.summary()['activitySeq'], first['seq'])
        restored = SessionStore(Path(self.temp.name))
        self.addCleanup(restored.database.close)
        self.assertEqual(restored.list_summaries()[0]['activitySeq'], second['seq'])
        cancelled = log.append('turn.cancelled')
        self.assertEqual((self.summary()['activitySeq'], self.summary()['status']), (cancelled['seq'], 'cancelled'))

    def test_legacy_database_replays_fully_projected_history_and_migration_is_idempotent(self):
        log = self.session.events
        self.store.update(self.session.id, title='keep title', pinned=True)
        for event_type in ('turn.started', 'turn.failed', 'turn.started', 'report.submitted',
                           'turn.completed', 'model.changed'):
            log.append(event_type, prompt='auto title')
        expected = self.summary()
        self.store.database.close()
        # Remove the added column to reproduce an existing pre-migration DB
        # whose event_seq was already current but whose status was stale.
        with sqlite3.connect(Path(self.temp.name) / 'chat_ai.sqlite3') as db:
            db.execute('ALTER TABLE sessions DROP COLUMN activity_seq')
            db.execute("UPDATE sessions SET status='failed'")
        original_journal = log.path.read_bytes()
        for _ in range(2):
            restored = SessionStore(Path(self.temp.name))
            try:
                self.assertEqual(restored.list_summaries(), [expected])
                self.assertEqual(log.path.read_bytes(), original_journal)
                with restored.database.connect() as db:
                    row = db.execute('SELECT event_seq, activity_seq, status FROM sessions').fetchone()
                self.assertEqual(tuple(row), (6, 5, 'submitted'))
            finally:
                restored.database.close()

    def test_failed_projection_can_be_repaired_from_authoritative_journal(self):
        received = []
        log = self.store.open(self.session.id, received.append).events
        with self.store.database.connect(write=True) as connection:
            connection.execute("""CREATE TRIGGER reject_title BEFORE UPDATE OF auto_title ON sessions
                WHEN NEW.auto_title='reject' BEGIN SELECT RAISE(ABORT, 'test rollback'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            log.append('turn.started', prompt='reject')
        self.assertEqual([item['seq'] for item in log.read()], [1])
        self.assertTrue(self.summary()['empty'])
        self.assertEqual(received, [])
        with self.store.database.connect(write=True) as connection:
            connection.execute('DROP TRIGGER reject_title')
        log.repair_summary()
        self.assertEqual(self.summary()['title'], 'reject')
        record = log.append('turn.started', prompt='accepted')
        self.assertEqual(record['seq'], 2)
        self.assertEqual(received, [record])
        with self.store.database.connect(write=True) as connection:
            connection.execute('''CREATE TRIGGER reject_activity BEFORE UPDATE OF activity_seq ON sessions
                WHEN NEW.activity_seq > OLD.activity_seq BEGIN SELECT RAISE(ABORT, 'test rollback'); END''')
        with self.assertRaises(sqlite3.IntegrityError):
            log.append('turn.failed', reason='recover this failure')
        self.assertEqual((self.summary()['activitySeq'], self.summary()['status']), (0, 'running'))
        with self.store.database.connect(write=True) as connection:
            connection.execute('DROP TRIGGER reject_activity')
        log.repair_summary()
        self.assertEqual((self.summary()['activitySeq'], self.summary()['status']), (3, 'failed'))


if __name__ == '__main__':
    unittest.main()

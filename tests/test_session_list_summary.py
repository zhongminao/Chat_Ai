import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.storage.session import SessionStore


class SessionListSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SessionStore(Path(self.temp.name))
        self.session = self.store.create()

    def tearDown(self):
        self.temp.cleanup()

    def summary(self):
        return next(item for item in self.store.list_summaries() if item['id'] == self.session.id)

    def test_persisted_summary_does_not_parse_event_bodies(self):
        self.session.events.append('turn.started', prompt='hello summary', images=[])
        self.session.events.append('report.submitted', content='# Large report body')
        initial = self.summary()
        self.assertEqual((initial['title'], initial['status'], initial['empty']), ('hello summary', 'submitted', False))
        with patch('agent.storage.event_log.json.loads', side_effect=AssertionError('summary must not parse events')):
            restored = SessionStore(Path(self.temp.name)).list_summaries()
            self.assertEqual(restored, [initial])
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
        self.store.rename(self.session.id, 'custom title')
        self.assertEqual(self.summary()['title'], 'custom title')
        self.store.delete(self.session.id)
        self.assertFalse(self.session.directory.exists())
        self.assertEqual(self.store.list_summaries(), [])

    def test_event_and_summary_rollback_together_and_publish_after_commit(self):
        received = []
        def committed(event):
            received.append((self.summary(), self.store.open(self.session.id).events.read()))
        log = self.store.open(self.session.id, committed).events
        # Fail after the INSERT, while updating the summary in the same transaction.
        with self.store.database.connect(write=True) as connection:
            connection.execute("""CREATE TRIGGER reject_title BEFORE UPDATE OF auto_title ON sessions
                WHEN NEW.auto_title='reject' BEGIN SELECT RAISE(ABORT, 'test rollback'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            log.append('turn.started', prompt='reject')
        self.assertEqual(log.read(), [])
        self.assertTrue(self.summary()['empty'])
        self.assertEqual(received, [])
        record = log.append('turn.started', prompt='accepted')
        self.assertEqual(record['seq'], 1)
        self.assertEqual(received[0][0]['title'], 'accepted')
        self.assertEqual(received[0][1], [record])


if __name__ == '__main__':
    unittest.main()

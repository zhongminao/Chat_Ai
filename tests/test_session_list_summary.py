import json
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

    def read_list_summary(self):
        return self.store.read_list_summary(self.session.id)

    def test_reuses_persisted_summary_and_only_parses_appended_events(self):
        self.session.events.append('turn.started', prompt='hello summary', images=[])
        self.session.events.append('report.submitted', content='# Large report body')
        initial = self.read_list_summary()
        self.assertEqual((initial['title'], initial['status'], initial['empty']), ('hello summary', 'submitted', False))
        original = json.loads
        with patch('agent.storage.session.json.loads', wraps=original) as loads:
            # A new store also reuses the on-disk summary after a service restart.
            restored = SessionStore(Path(self.temp.name)).read_list_summary(self.session.id)
            self.assertEqual(restored, initial)
            parsed = [original(c.args[0]) for c in loads.call_args_list]
            self.assertFalse(any('type' in value for value in parsed))
        self.session.events.append('turn.failed', reason='later failure')
        with patch('agent.storage.session.json.loads', wraps=original) as loads:
            updated = self.read_list_summary()
            parsed = [original(c.args[0]) for c in loads.call_args_list]
            self.assertEqual([v['type'] for v in parsed if 'type' in v], ['turn.failed'])
        self.assertEqual(updated['status'], 'failed')
        self.assertEqual(updated['title'], 'hello summary')
        self.assertGreater(updated['updatedAt'], initial['updatedAt'])
        self.assertNotIn('Large report body', (self.session.directory / 'summary.json').read_text())

    def test_empty_images_rename_and_delete(self):
        self.assertTrue(self.read_list_summary()['empty'])
        self.assertEqual(self.read_list_summary()['title'], '新会话')
        self.session.events.append('model.changed', new={'name': 'test'})
        self.assertTrue(self.read_list_summary()['empty'])
        self.session.events.append('turn.started', prompt='', images=[{'id': 'image'}])
        self.assertEqual(self.read_list_summary()['title'], '图片对话')
        self.assertFalse(self.read_list_summary()['empty'])
        self.store.rename(self.session.id, 'custom title')
        self.assertEqual(self.read_list_summary()['title'], 'custom title')
        self.store.delete(self.session.id)
        self.assertFalse(self.session.directory.exists())

    def test_rebuilds_after_truncation_or_invalid_cache_and_ignores_partial_tail(self):
        self.session.events.append('turn.started', prompt='old title', images=[])
        self.read_list_summary()
        # Replace/truncate an imported or repaired event log.
        path = self.session.events.path
        event = {'seq': 1, 'time': 10**9, 'type': 'turn.started', 'prompt': 'new', 'images': []}
        path.write_text(json.dumps(event) + '\n')
        self.assertEqual(self.read_list_summary()['title'], 'new')
        (self.session.directory / 'summary.json').write_text('{broken')
        self.assertEqual(self.read_list_summary()['title'], 'new')
        pending = json.dumps({'seq': 2, 'time': 2 * 10**9, 'type': 'turn.cancelled'})
        with path.open('a') as file:
            file.write(pending)
        self.assertEqual(self.read_list_summary()['status'], 'idle')
        with path.open('a') as file:
            file.write('\n')
        self.assertEqual(self.read_list_summary()['status'], 'cancelled')


if __name__ == '__main__':
    unittest.main()

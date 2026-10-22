"""History properties are durable metadata, independent of event projections."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.storage.session import SessionStore
from agent.web import app as web


class SessionPropertiesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SessionStore(Path(self.temp.name))
        self.addCleanup(self.store.database.close)
        self.session = self.store.create(custom={'keep': '原数据'})
        self.registry = SimpleNamespace(items={})
        self.enterContext(patch.object(web, 'session_store', self.store))
        self.enterContext(patch.object(web, 'registry', self.registry))
        self.client = self.enterContext(TestClient(web.app))
        self.path = f'/api/sessions/{self.session.id}'

    def summary(self, identifier=None):
        response = self.client.get('/api/sessions')
        self.assertEqual(response.status_code, 200)
        return next(row for row in response.json()['sessions'] if row['id'] == (identifier or self.session.id))

    def test_old_metadata_defaults_and_all_sessions_remain_visible(self):
        # A row created by the old implementation has no pin/archive keys.
        with self.store.database.connect() as connection:
            row = connection.execute('SELECT metadata FROM sessions WHERE id=?', (self.session.id,)).fetchone()
        self.assertEqual(json.loads(row['metadata']), {'custom': {'keep': '原数据'}})
        self.assertIs(self.summary()['pinned'], False)
        self.assertIs(self.summary()['archived'], False)
        other = self.store.create()
        child = self.store.create(parent_session_id=self.session.id)
        before = [row['id'] for row in self.store.list_summaries()]
        self.assertEqual(self.client.patch(self.path, json={'pinned': True, 'archived': True}).status_code, 200)
        result = self.client.get('/api/sessions').json()['sessions']
        self.assertEqual([row['id'] for row in result], before)
        self.assertEqual({row['id'] for row in result}, {self.session.id, other.id, child.id})
        for row in result:
            self.assertIs(type(row['pinned']), bool)
            self.assertIs(type(row['archived']), bool)

    def test_combined_update_persists_preserves_metadata_and_survives_events(self):
        before = self.summary()
        response = self.client.patch(self.path, json={'title': '  项目名称  ', 'pinned': True, 'archived': True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'id': self.session.id, 'title': '项目名称', 'pinned': True, 'archived': True})
        self.assertEqual(self.summary()['updatedAt'], before['updatedAt'])
        self.session.events.append('turn.started', prompt='auto title', images=[])
        self.assertEqual(self.store.metadata(self.session.id)['custom'], {'keep': '原数据'})
        # Close and reopen the actual database, as on process restart.
        self.store.database.close()
        restored = SessionStore(Path(self.temp.name))
        try:
            summary = restored.list_summaries()[0]
            self.assertEqual((summary['title'], summary['pinned'], summary['archived']), ('项目名称', True, True))
            with patch.object(web, 'session_store', restored):
                self.assertEqual(self.client.patch(self.path, json={'archived': False}).json(),
                                 {'id': self.session.id, 'archived': False})
                self.assertTrue(self.summary()['pinned'])
                self.assertFalse(self.summary()['archived'])
                self.assertEqual(self.client.patch(self.path, json={'pinned': False}).json(),
                                 {'id': self.session.id, 'pinned': False})
        finally:
            restored.database.close()

    def test_rename_contract_and_validation_are_unchanged(self):
        response = self.client.patch(self.path, json={'title': '  新名称  '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'id': self.session.id, 'title': '新名称'})
        self.assertEqual(self.summary()['title'], '新名称')
        for title in ('', '   ', 'x' * 81, 'hello\nworld', 'a\x00b', 'a\x7fb'):
            with self.subTest(title=repr(title)):
                response = self.client.patch(self.path, json={'title': title, 'pinned': True})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(self.summary()['pinned'])
                self.assertEqual(self.summary()['title'], '新名称')
        self.assertEqual(self.client.patch(self.path, json={'title': 'x' * 80}).status_code, 200)

    def test_invalid_request_types_are_rejected_without_changes(self):
        invalid = [{}, {'unknown': True}, {'title': None}, {'title': 12}, {'title': []}]
        for key in ('pinned', 'archived'):
            invalid.extend({key: value} for value in (None, 0, 1, 'true', 'false', [], {}))
        invalid.extend([{'pinned': True, 'archived': 'false'}, {'pinned': True, 'extra': 1}])
        before = self.summary()
        for body in invalid:
            with self.subTest(body=body):
                self.assertEqual(self.client.patch(self.path, json=body).status_code, 422)
                self.assertEqual(self.summary(), before)
        self.assertEqual(self.client.patch(self.path, content='{', headers={'content-type': 'application/json'}).status_code, 422)

    def test_missing_and_child_sessions_cannot_be_modified(self):
        child = self.store.create(parent_session_id=self.session.id, title='子任务')
        before = self.store.metadata(child.id)
        for changes in ({'title': 'rename'}, {'pinned': True}, {'archived': True},
                        {'title': 'rename', 'pinned': True, 'archived': True}):
            with self.subTest(changes=changes):
                self.assertEqual(self.client.patch('/api/sessions/missing', json=changes).status_code, 404)
                self.assertEqual(self.client.patch(f'/api/sessions/{child.id}', json=changes).status_code, 400)
                self.assertEqual(self.store.metadata(child.id), before)
        self.assertFalse(self.summary(child.id)['pinned'])
        self.assertFalse(self.summary(child.id)['archived'])


if __name__ == '__main__':
    unittest.main()

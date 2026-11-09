"""History properties are durable metadata, independent of event projections."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
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
        self.assertIsNone(self.summary()['archivedAt'])
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
        instant = datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc)
        journal = self.session.events.path.read_bytes()
        with patch('agent.storage.session.datetime') as clock:
            clock.now.return_value = instant
            response = self.client.patch(self.path, json={'title': '  项目名称  ', 'pinned': True, 'archived': True})
            clock.now.assert_called_once_with(timezone.utc)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'id': self.session.id, 'title': '项目名称', 'pinned': False,
                                          'archived': True, 'archivedAt': instant.timestamp()})
        self.assertEqual(self.summary()['updatedAt'], before['updatedAt'])
        self.assertEqual(self.summary()['activitySeq'], before['activitySeq'])
        self.assertEqual(self.session.events.path.read_bytes(), journal)
        self.session.events.append('turn.started', prompt='auto title', images=[])
        self.assertEqual(self.store.metadata(self.session.id)['custom'], {'keep': '原数据'})
        self.assertEqual(self.summary()['archivedAt'], instant.timestamp())
        self.assertFalse(self.summary()['pinned'])
        # Event activity keeps its existing recency behavior, not the archive timestamp.
        self.assertGreater(self.summary()['updatedAt'], before['updatedAt'])
        # Close and reopen the actual database, as on process restart.
        self.store.database.close()
        restored = SessionStore(Path(self.temp.name))
        try:
            summary = restored.list_summaries()[0]
            self.assertEqual((summary['title'], summary['pinned'], summary['archived']), ('项目名称', False, True))
            self.assertEqual(summary['archivedAt'], instant.timestamp())
            with patch.object(web, 'session_store', restored):
                self.assertEqual(self.client.patch(self.path, json={'archived': False}).json(),
                                 {'id': self.session.id, 'archived': False, 'archivedAt': None, 'pinned': False})
                self.assertFalse(self.summary()['pinned'])
                self.assertFalse(self.summary()['archived'])
                self.assertIsNone(self.summary()['archivedAt'])
                self.assertEqual(self.client.patch(self.path, json={'pinned': True}).json(),
                                 {'id': self.session.id, 'pinned': True})
        finally:
            restored.database.close()

    def test_archive_transitions_are_server_timed_idempotent_and_do_not_change_recency(self):
        self.assertEqual(self.client.patch(self.path, json={'pinned': True}).status_code, 200)
        before = self.summary()
        journal = self.session.events.path.read_bytes()
        first = datetime(2026, 2, 3, 4, 5, 6, 123456, tzinfo=timezone.utc)
        second = datetime(2026, 3, 4, 5, 6, 7, 654321, tzinfo=timezone.utc)
        with patch('agent.storage.session.datetime') as clock:
            clock.now.return_value = first
            self.assertEqual(self.client.patch(self.path, json={'archived': True}).json(),
                             {'id': self.session.id, 'archived': True, 'archivedAt': first.timestamp(), 'pinned': False})
            clock.now.assert_called_once_with(timezone.utc)
            clock.now.reset_mock()
            for changes in ({'archived': True}, {'pinned': True},
                            {'archived': True, 'pinned': True}, {'title': 'renamed'}):
                with self.subTest(changes=changes):
                    response = self.client.patch(self.path, json=changes)
                    self.assertEqual(response.status_code, 200)
                    self.assertIs(response.json()['pinned'], False)
                    self.assertEqual(self.summary()['archivedAt'], first.timestamp())
                    self.assertFalse(self.summary()['pinned'])
                    self.assertEqual(self.summary()['updatedAt'], before['updatedAt'])
                    self.assertEqual(self.summary()['activitySeq'], before['activitySeq'])
            clock.now.assert_not_called()
            self.assertEqual(self.client.patch(self.path, json={'archived': False}).json(),
                             {'id': self.session.id, 'archived': False, 'archivedAt': None, 'pinned': False})
            self.assertIsNone(self.store.metadata(self.session.id)['archivedAt'])
            self.assertFalse(self.summary()['pinned'])
            self.assertEqual(self.client.patch(self.path, json={'archived': False}).json(),
                             {'id': self.session.id, 'archived': False, 'archivedAt': None})
            clock.now.assert_not_called()
            clock.now.return_value = second
            self.assertEqual(self.client.patch(self.path, json={'archived': True}).json(),
                             {'id': self.session.id, 'archived': True, 'archivedAt': second.timestamp(), 'pinned': False})
            clock.now.assert_called_once_with(timezone.utc)
        self.assertEqual(self.summary()['archivedAt'], second.timestamp())
        self.assertEqual(self.summary()['updatedAt'], before['updatedAt'])
        self.assertEqual(self.summary()['activitySeq'], before['activitySeq'])
        self.assertEqual(self.session.events.path.read_bytes(), journal)
        self.assertEqual(self.store.metadata(self.session.id)['custom'], {'keep': '原数据'})

    def test_legacy_archived_metadata_stays_unknown_without_fabricating_dates(self):
        # Includes the old pinned+archived combination, without a stored archive date.
        legacy = self.store.create(archived=True, pinned=True, custom={'keep': '旧数据'})
        path = f'/api/sessions/{legacy.id}'
        before = self.summary(legacy.id)
        self.assertIsNone(before['archivedAt'])
        self.assertFalse(before['pinned'])
        original_metadata = self.store.metadata(legacy.id)
        self.assertNotIn('archivedAt', original_metadata)
        self.assertTrue(original_metadata['pinned'])  # Listing must not mutate legacy rows.
        with patch('agent.storage.session.datetime') as clock:
            self.assertEqual(self.client.patch(path, json={'title': '旧归档改名'}).json(),
                             {'id': legacy.id, 'title': '旧归档改名', 'pinned': False})
            self.assertNotIn('archivedAt', self.store.metadata(legacy.id))
            for changes in ({'archived': True}, {'archived': True, 'pinned': True}, {'pinned': True}):
                with self.subTest(changes=changes):
                    response = self.client.patch(path, json=changes)
                    self.assertEqual(response.status_code, 200)
                    self.assertFalse(response.json()['pinned'])
                    self.assertIsNone(self.summary(legacy.id)['archivedAt'])
            self.assertEqual(self.summary(legacy.id)['updatedAt'], before['updatedAt'])
            self.assertEqual(self.summary(legacy.id)['activitySeq'], before['activitySeq'])
            self.assertEqual(self.store.metadata(legacy.id)['custom'], {'keep': '旧数据'})
            clock.now.assert_not_called()
        # Directly unarchiving an untouched legacy row must not resurrect its stale pin.
        untouched = self.store.create(archived=True, pinned=True)
        self.assertEqual(self.store.update(untouched.id, archived=False),
                         {'archived': False, 'archivedAt': None, 'pinned': False})
        self.assertFalse(self.store.metadata(untouched.id)['pinned'])
        # A zero timestamp is known, not a missing value, and must not be refreshed.
        epoch = self.store.create(archived=True, archivedAt=0)
        with patch('agent.storage.session.datetime') as clock:
            self.assertEqual(self.store.update(epoch.id, archived=True),
                             {'archived': True, 'archivedAt': 0, 'pinned': False})
            clock.now.assert_not_called()
        # Explicitly requesting a pin is allowed once the final state is unarchived.
        self.assertEqual(self.store.update(epoch.id, archived=False, pinned=True),
                         {'archived': False, 'archivedAt': None, 'pinned': True})
        self.assertTrue(self.summary(epoch.id)['pinned'])
        # A stale date on an unarchived row must not be reused on a new transition.
        stale = self.store.create(archived=False, archivedAt=123)
        instant = datetime(2026, 4, 5, tzinfo=timezone.utc)
        with patch('agent.storage.session.datetime') as clock:
            clock.now.return_value = instant
            self.assertEqual(self.store.update(stale.id, archived=True),
                             {'archived': True, 'archivedAt': instant.timestamp(), 'pinned': False})
            clock.now.assert_called_once_with(timezone.utc)

    def test_summary_archive_date_is_numeric_or_null_and_requires_archive_state(self):
        cases = [({}, None), ({'archived': True}, None),
                 ({'archived': True, 'archivedAt': None}, None),
                 ({'archived': True, 'archivedAt': 0}, 0),
                 ({'archived': True, 'archivedAt': 123.5}, 123.5),
                 ({'archived': True, 'archivedAt': '123'}, None),
                 ({'archived': True, 'archivedAt': True}, None),
                 ({'archived': True, 'archivedAt': []}, None),
                 ({'archived': True, 'archivedAt': {}}, None),
                 ({'archived': False, 'archivedAt': 123}, None),
                 ({'archived': 'true', 'archivedAt': 123}, None)]
        for metadata, expected in cases:
            with self.subTest(metadata=metadata):
                session = self.store.create(**metadata)
                self.assertEqual(self.summary(session.id)['archivedAt'], expected)
                self.assertEqual({key: value for key, value in self.store.metadata(session.id).items()
                                  if key not in {'id', 'createdAt'}}, metadata)
                if metadata.get('archived') is True:
                    with patch('agent.storage.session.datetime') as clock:
                        response = self.client.patch(f'/api/sessions/{session.id}', json={'archived': True})
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json(), {'id': session.id, 'archived': True,
                                                          'archivedAt': expected, 'pinned': False})
                        self.assertEqual(self.summary(session.id)['archivedAt'], expected)
                        clock.now.assert_not_called()

    def test_rename_contract_and_validation_are_unchanged(self):
        before = self.summary()
        journal = self.session.events.path.read_bytes()
        response = self.client.patch(self.path, json={'title': '  新名称  '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'id': self.session.id, 'title': '新名称'})
        self.assertEqual(self.summary()['title'], '新名称')
        self.assertIsNone(self.summary()['archivedAt'])
        self.assertEqual(self.summary()['updatedAt'], before['updatedAt'])
        self.assertEqual(self.summary()['activitySeq'], before['activitySeq'])
        self.assertEqual(self.session.events.path.read_bytes(), journal)
        for title in ('', '   ', 'x' * 81, 'hello\nworld', 'a\x00b', 'a\x7fb'):
            with self.subTest(title=repr(title)):
                response = self.client.patch(self.path, json={'title': title, 'pinned': True})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(self.summary()['pinned'])
                self.assertEqual(self.summary()['title'], '新名称')
        self.assertEqual(self.client.patch(self.path, json={'title': 'x' * 80}).status_code, 200)

    def test_invalid_request_types_are_rejected_without_changes(self):
        invalid = [{}, {'unknown': True}, {'title': None}, {'title': 12}, {'title': []},
                   {'archivedAt': 123}, {'archived': True, 'archivedAt': 123}]
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

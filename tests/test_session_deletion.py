import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from agent.core.session_registry import SessionRegistry
from agent.core.session_runtime import SessionBusy
from agent.web import app as web
from agent.workflow.config import load


class SessionDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.registry = SessionRegistry(replace(load(), storage_dir=self.root, workspace=self.root / 'workspace', mcp={}))
        self.runtimes = []

    def tearDown(self):
        for runtime in self.runtimes:
            runtime.busy = False
            runtime.queue.put(None)
            runtime.worker.join(5)
            self.assertFalse(runtime.worker.is_alive())
        self.registry.store.database.close()
        self.temp.cleanup()

    def create(self, parent=None, terminal='turn.completed'):
        runtime = self.registry.create(**({'parent_session_id': parent.session.id} if parent else {}))
        self.runtimes.append(runtime)
        session = runtime.session
        session.events.append('turn.started', prompt='test')
        report = session.directory / 'reports' / 'test.md'
        report.parent.mkdir()
        report.write_text('test report')
        session.events.append(terminal, result_path=str(report), content='test report')
        data = BytesIO()
        Image.new('RGB', (20, 10), 'blue').save(data, format='PNG')
        session.images.add(data.getvalue(), 'test.png')
        return runtime

    def client(self):
        self.enterContext(patch.object(web, 'registry', self.registry))
        self.enterContext(patch.object(web, 'session_store', self.registry.store))
        return self.enterContext(TestClient(web.app))

    def assert_present(self, runtimes):
        for runtime in runtimes:
            self.assertEqual(self.registry.store.metadata(runtime.session.id)['id'], runtime.session.id)
            self.assertTrue((runtime.session.directory / 'reports/test.md').is_file())
            self.assertTrue(runtime.session.images.list())
            self.assertFalse(runtime.closed)
            self.assertIs(self.registry.items[runtime.session.id], runtime)

    def test_delete_main_removes_ended_children_reports_images_events_and_monitors(self):
        main = self.create()
        children = [self.create(main, terminal=status) for status in
                    ['report.submitted', 'turn.failed', 'turn.cancelled']]
        other = self.create()
        monitor = self.registry.monitor(main.session.id)
        self.assertEqual(len(monitor.watch()['changes']), 3)
        targets = [main, *children]
        ids = [runtime.session.id for runtime in targets]
        client = self.client()
        self.assertEqual(client.delete(f'/api/sessions/{main.session.id}').status_code, 200)
        for runtime in targets:
            runtime.worker.join(5)
            self.assertTrue(runtime.closed)
            self.assertFalse(runtime.worker.is_alive())
            self.assertFalse(runtime.session.directory.exists())
            self.assertNotIn(runtime.session.id, self.registry.items)
            self.assertNotIn(runtime.session.id, self.registry.monitors)
        with self.registry.store.database.connect() as connection:
            for table, column in [('sessions', 'id'), ('events', 'session_id'),
                                  ('images', 'session_id'), ('monitors', 'session_id')]:
                count = connection.execute(
                    f'SELECT COUNT(*) FROM {table} WHERE {column} IN ({",".join("?" for _ in ids)})', ids).fetchone()[0]
                self.assertEqual(count, 0, table)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assert_present([other])
        self.assertEqual(client.delete(f'/api/sessions/{main.session.id}').status_code, 404)

    def test_running_main_or_any_child_blocks_entire_deletion(self):
        main = self.create()
        children = [self.create(main), self.create(main)]
        targets = [main, *children]
        client = self.client()
        for active in targets:
            with self.subTest(active=active.session.id):
                active.busy = True
                try:
                    response = client.delete(f'/api/sessions/{main.session.id}')
                    self.assertEqual(response.status_code, 409)
                    self.assertIn('请先停止', response.json()['detail'])
                    self.assertTrue(active.busy, 'deletion must not stop the task')
                    self.assert_present(targets)
                finally:
                    active.busy = False

    def test_deleting_one_child_keeps_parent_and_sibling_and_updates_monitor(self):
        main = self.create()
        child = self.create(main)
        sibling = self.create(main)
        monitor = self.registry.monitor(main.session.id)
        cursor = monitor.watch()['cursor']
        self.registry.delete(child.session.id)
        self.assert_present([main, sibling])
        self.assertFalse(child.session.directory.exists())
        self.assertTrue(child.closed)
        self.assertEqual([item['session_id'] for item in monitor.watch()['changes']], [sibling.session.id])
        self.assertTrue(monitor.watch(cursor=cursor)['changes'][0]['deleted'])

    def test_reloaded_registry_deletes_children_without_starting_their_runtimes(self):
        main = self.create()
        child = self.create(main)
        restored = SessionRegistry(self.registry.config)
        try:
            with patch.object(restored, 'get', side_effect=AssertionError('deletion must not open an Agent')):
                restored.delete(main.session.id)
            self.assertEqual(restored.items, {})
            self.assertFalse(main.session.directory.exists())
            self.assertFalse(child.session.directory.exists())
        finally:
            restored.store.database.close()

    def test_database_failure_rolls_back_every_session_before_removing_files(self):
        main = self.create()
        child = self.create(main)
        with self.registry.store.database.connect(write=True) as connection:
            connection.execute(f"""CREATE TRIGGER deny_delete BEFORE DELETE ON sessions
                WHEN OLD.id = '{main.session.id}' BEGIN SELECT RAISE(ABORT, 'delete denied'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'delete denied'):
            self.registry.delete(main.session.id)
        self.assert_present([main, child])

    def test_start_cannot_race_with_a_successful_deletion(self):
        main = self.create()
        entered, release = threading.Event(), threading.Event()
        delete = self.registry.store.delete

        def paused_delete(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return delete(*args, **kwargs)

        with patch.object(self.registry.store, 'delete', side_effect=paused_delete), ThreadPoolExecutor(2) as pool:
            deletion = pool.submit(self.registry.delete, main.session.id)
            try:
                self.assertTrue(entered.wait(5))
                start = pool.submit(main.start, 'late input')
            finally:
                release.set()
            deletion.result(5)
            with self.assertRaises(SessionBusy):
                start.result(5)
        self.assertFalse(main.busy)
        self.assertTrue(main.closed)


if __name__ == '__main__':
    unittest.main()

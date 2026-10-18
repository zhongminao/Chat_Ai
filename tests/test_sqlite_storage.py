"""Storage transactions, concurrent writers, restart recovery and disk-backed images."""
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from agent.storage.session import SessionStore
from agent.storage.database import Database
from agent.workflow.message_replay import restore_model_messages


def png():
    output = BytesIO()
    Image.new('RGB', (20, 10), 'blue').save(output, format='PNG')
    return output.getvalue()


class SQLiteStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.new_store()
        self.session = self.store.create(model={'provider': 'test', 'name': 'model'})

    def new_store(self):
        store = SessionStore(self.root)
        self.addCleanup(store.database.close)
        return store

    def test_connection_reused_across_threads_with_per_transaction_sync_mode(self):
        def transaction(durable):
            with self.store.database.connect(write=True, durable=durable) as connection:
                return (id(connection), connection.execute('PRAGMA synchronous').fetchone()[0],
                        connection.execute('PRAGMA journal_mode').fetchone()[0])
        modes = [False, True] * 8
        with ThreadPoolExecutor(4) as pool:
            results = list(pool.map(transaction, modes))
        self.assertEqual(len({row[0] for row in results}), 1)
        self.assertEqual([row[1] for row in results], [2 if mode else 1 for mode in modes])
        self.assertEqual({row[2] for row in results}, {'wal'})

    def test_events_published_after_commit_and_end_events_use_full(self):
        observer = self.new_store().open(self.session.id).events
        published = []
        def on_event(event):
            self.assertEqual(observer.read(event['seq'] - 1), [event])
            with self.store.database.connect() as connection:
                published.append((event['type'], connection.execute('PRAGMA synchronous').fetchone()[0]))
        self.session.events.on_append = on_event
        self.session.events.append('message.delta', durable=False, text='hello')
        self.session.events.append('turn.completed', answer='hello')
        self.session.events.append('message.delta', durable=False, text='partial')
        self.session.events.append('turn.cancelled', answer='partial')
        self.assertEqual(published, [('message.delta', 1), ('turn.completed', 2),
                                     ('message.delta', 1), ('turn.cancelled', 2)])

    def test_wal_reader_sees_only_committed_data_and_failed_transaction_rolls_back(self):
        observer = self.new_store()
        original = observer.metadata(self.session.id)
        with self.assertRaisesRegex(RuntimeError, 'abort'):
            with self.store.database.connect(write=True, durable=False) as connection:
                connection.execute('UPDATE sessions SET title=? WHERE id=?', ('uncommitted', self.session.id))
                self.assertEqual(observer.metadata(self.session.id), original)
                raise RuntimeError('abort')
        self.assertEqual(observer.metadata(self.session.id), original)
        self.store.rename(self.session.id, 'committed')
        self.assertEqual(observer.metadata(self.session.id)['title'], 'committed')

    def test_committed_wal_survives_writer_process_kill(self):
        ready = self.root / 'writer-ready'
        script = '''from pathlib import Path
from agent.storage.session import SessionStore
import sys, time
store = SessionStore(Path(sys.argv[1]))
log = store.open(sys.argv[2]).events
log.append('message.delta', durable=False, text='first')
log.append('turn.completed', answer='first')
log.append('message.delta', durable=False, text='second')
Path(sys.argv[3]).touch()
time.sleep(60)
'''
        process = subprocess.Popen([sys.executable, '-c', script, str(self.root), self.session.id, str(ready)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 15
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(ready.exists(), 'writer failed to commit before timeout')
            self.assertTrue(Path(str(self.store.database.path) + '-wal').is_file())
            process.kill()
            process.communicate(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        restored = self.new_store().open(self.session.id)
        self.assertEqual([event['type'] for event in restored.events.read()],
                         ['message.delta', 'turn.completed', 'message.delta'])
        self.assertEqual(restored.events.read()[-1]['text'], 'second')
        self.assertEqual(restored.events.append('turn.cancelled')['seq'], 4)
        with self.store.database.connect() as connection:
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_unsafe_sqlite_version_rejected_before_opening_database(self):
        path = self.root / 'unsafe.sqlite3'
        with patch('agent.storage.database.sqlite3.sqlite_version_info', (3, 45, 3)), \
             self.assertRaisesRegex(RuntimeError, 'SQLite 3.51.3'):
            Database(path)
        self.assertFalse(path.exists())

    def test_reopen_preserves_metadata_events_compacted_messages_and_image_files(self):
        image = self.session.images.add(png(), 'plot.png')
        messages = [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': 'summary', 'images': [image['id']]}]
        self.session.events.append('context.compacted', messages=messages)
        self.session.images.rename(image['id'], '结果图')
        self.store.rename(self.session.id, '重启恢复')
        reopened = self.new_store()
        restored = reopened.open(self.session.id)
        self.assertEqual(reopened.metadata(self.session.id)['title'], '重启恢复')
        self.assertEqual(reopened.metadata(self.session.id)['model'], {'provider': 'test', 'name': 'model'})
        self.assertEqual(restored.events.read(), self.session.events.read())
        self.assertEqual(restore_model_messages(restored.events.read(), messages[0]), messages)
        self.assertEqual(restored.images.list()[0]['name'], '结果图')
        self.assertEqual(restored.images.path(image['id']).read_bytes(), png())
        self.assertTrue(restored.images.path(image['id'], preview=True).is_file())
        self.assertEqual(list(self.root.rglob('*.json')), [])
        self.assertEqual(list(self.root.rglob('*.jsonl')), [])
        with reopened.database.connect() as connection:
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_multiple_handles_allocate_event_sequences_atomically(self):
        logs = [self.new_store().open(self.session.id).events for _ in range(4)]
        def append(index):
            for number in range(15):
                logs[index].append('message.delta', durable=False, text=f'{index}:{number}')
        with ThreadPoolExecutor(4) as pool:
            list(pool.map(append, range(4)))
        records = self.session.events.read()
        self.assertEqual([record['seq'] for record in records], list(range(1, 61)))
        self.assertEqual(len({record['text'] for record in records}), 60)
        self.assertEqual(self.session.events.read(57), records[57:])

    def test_separate_processes_share_sequences_without_file_locks(self):
        script = ('from pathlib import Path; from agent.storage.session import SessionStore; import sys; '
                  'log=SessionStore(Path(sys.argv[1])).open(sys.argv[2]).events; '
                  '[log.append("worker", durable=False, worker=sys.argv[3], number=n) for n in range(12)]')
        processes = [subprocess.Popen([sys.executable, '-c', script, str(self.root), self.session.id, str(i)],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True) for i in range(2)]
        try:
            for process in processes:
                _, error = process.communicate(timeout=60)
                self.assertEqual(process.returncode, 0, error)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        records = self.session.events.read()
        self.assertEqual([record['seq'] for record in records], list(range(1, 25)))
        self.assertEqual({record['worker'] for record in records}, {'0', '1'})

    def test_serialization_failure_leaves_no_event_or_sequence_gap(self):
        with self.assertRaises(TypeError):
            self.session.events.append('bad', value=object())
        self.assertEqual(self.session.events.append('good')['seq'], 1)
        with self.assertRaises(ValueError):
            self.session.events.append('bad', seq=20)
        self.assertEqual(self.session.events.append('good')['seq'], 2)

    def test_concurrent_images_keep_unique_numbers_and_stable_paths(self):
        images = [self.store.open(self.session.id).images for _ in range(3)]
        with ThreadPoolExecutor(3) as pool:
            results = list(pool.map(lambda index: images[index % 3].add(png(), f'{index}.png'), range(9)))
        restored = self.new_store().open(self.session.id).images
        self.assertEqual([image['ordinal'] for image in restored.list()], list(range(1, 10)))
        self.assertEqual(len({image['id'] for image in results}), 9)
        self.assertTrue(all(restored.path(image['id']).is_file() for image in results))

    def test_image_metadata_failure_rolls_back_number_and_removes_both_files(self):
        with self.store.database.connect(write=True) as connection:
            connection.execute("""CREATE TRIGGER reject_image BEFORE INSERT ON images
                BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.session.images.add(png(), 'plot.png')
        self.assertEqual(self.session.images.list(), [])
        self.assertEqual(list(self.session.images.root.iterdir()), [])
        with self.store.database.connect(write=True) as connection:
            connection.execute('DROP TRIGGER reject_image')
        self.assertEqual(self.session.images.add(png(), 'plot.png')['ordinal'], 1)

    def test_parent_relationships_and_delete_cascade_preserve_other_sessions(self):
        child = self.store.create(parent_session_id=self.session.id)
        self.assertEqual(self.store.children(self.session.id), [child.id])
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.delete(self.session.id)
        self.assertTrue(self.session.directory.is_dir())
        self.store.delete(child.id)
        image = self.session.images.add(png(), 'plot.png')
        self.session.events.append('turn.started', prompt='delete me')
        self.store.save_monitor(self.session.id, 1, {'job': {'status': 'done'}})
        other = self.store.create(title='keep')
        self.store.delete(self.session.id)
        self.assertEqual([item['id'] for item in self.store.list_summaries()], [other.id])
        self.assertFalse(self.session.directory.exists())
        with self.store.database.connect() as connection:
            for table in ('events', 'images', 'monitors'):
                self.assertEqual(connection.execute(f'SELECT COUNT(*) FROM {table} WHERE session_id=?', (self.session.id,)).fetchone()[0], 0)
        with self.assertRaises(FileNotFoundError):
            self.store.open(self.session.id)
        with self.assertRaises(FileNotFoundError):
            self.session.images.get(image['id'])

    def test_invalid_parent_creation_leaves_no_directory_or_partial_row(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create(parent_session_id='missing')
        self.assertEqual(len(self.store.list_summaries()), 1)
        self.assertEqual([path.name for path in self.store.root.iterdir()], [self.session.id])
        with self.assertRaises(FileNotFoundError):
            self.store.path('../outside')


if __name__ == '__main__':
    unittest.main()

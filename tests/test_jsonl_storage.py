"""JSONL is the event authority; SQLite holds only a recoverable listing projection."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent.storage.session import SessionStore
from agent.workflow.message_replay import restore_display_messages, restore_model_messages


class JSONLStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.new_store()
        self.session = self.store.create()
        self.assertEqual(self.session.events.path, self.session.directory / 'events.jsonl')
        self.assertEqual(self.session.events.path.read_bytes(), b'')

    def new_store(self):
        store = SessionStore(self.root)
        self.addCleanup(store.database.close)
        return store

    def projected(self):
        with self.store.database.connect() as db:
            row = db.execute('SELECT event_seq, auto_title, empty, status FROM sessions WHERE id=?',
                             (self.session.id,)).fetchone()
            return tuple(row)

    def test_streaming_does_not_update_sqlite_per_delta_and_boundary_repairs_summary(self):
        log = self.session.events
        first = log.append('turn.started', prompt='hello')
        log.append('model.started')
        for text in 'stream':
            log.append('message.delta', durable=False, text=text)
        self.assertEqual(self.projected()[0], 2)
        self.assertEqual(len(log.read()), 8)
        with self.store.database.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
        completed = log.append('model.completed')
        self.assertEqual(self.projected(), (completed['seq'], 'hello', 0, 'idle'))
        self.assertEqual([r['seq'] for r in log.read(first['seq'])], list(range(2, 10)))
        self.assertEqual(self.store.list_summaries()[0]['title'], 'hello')
        self.assertEqual(len(log.path.read_bytes().splitlines()), 9)

    def test_restart_reprojects_unprojected_stream_and_terminal_status(self):
        log = self.session.events
        log.append('turn.started', prompt='  first   line  ')
        log.append('message.delta', durable=False, text='unprojected')
        self.assertEqual(self.projected()[0], 1)
        restored = self.new_store()
        self.assertEqual(self.projected(), (2, 'first line', 0, 'idle'))
        self.assertEqual(restored.open(self.session.id).events.append('turn.cancelled', answer='partial')['seq'], 3)
        self.assertEqual(self.projected(), (3, 'first line', 0, 'cancelled'))

    def test_compacted_model_context_and_full_display_history_survive_restart(self):
        log = self.session.events
        log.append('turn.started', prompt='old')
        system = {'role': 'system', 'content': 'system'}
        compacted = [system, {'role': 'assistant', 'content': 'summary'}]
        log.append('context.compacted', messages=compacted)
        log.append('turn.started', prompt='new')
        events = self.new_store().open(self.session.id).events.read()
        self.assertEqual(restore_model_messages(events, system),
                         [*compacted, {'role': 'user', 'content': 'new'}])
        self.assertEqual([m['content'] for m in restore_display_messages(events) if m['role'] == 'user'],
                         ['old', 'new'])
        self.assertEqual(events[1]['messages'], compacted)

    def test_threads_and_processes_allocate_contiguous_sequences(self):
        logs = [self.new_store().open(self.session.id).events for _ in range(3)]
        def writer(i):
            for n in range(10):
                logs[i].append('message.delta', durable=False, text=f'thread:{i}:{n}')
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(writer, range(3)))
        script = ('from pathlib import Path; import sys; from agent.storage.session import SessionStore; '
                  'store=SessionStore(Path(sys.argv[1])); log=store.open(sys.argv[2]).events; '
                  '[log.append("message.delta", durable=False, text=f"process:{sys.argv[3]}:{n}") '
                  'for n in range(10)]; store.database.close()')
        processes = [subprocess.Popen([sys.executable, '-c', script, str(self.root), self.session.id, str(i)],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                     for i in range(2)]
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
        self.assertEqual([r['seq'] for r in records], list(range(1, 51)))
        self.assertEqual(len({r['text'] for r in records}), 50)
        self.assertEqual(len(logs[0].read(48)), 2)
        self.assertEqual(self.new_store().open(self.session.id).events.append('turn.completed')['seq'], 51)

    def test_incomplete_tail_truncates_and_reuses_sequence(self):
        log = self.session.events
        first = log.append('turn.started', prompt='ok')
        with log.path.open('ab') as file:
            file.write(b'{"seq": 2, "time":')
        restored = self.new_store().open(self.session.id).events
        self.assertEqual(restored.read(), [first])
        self.assertEqual(restored.append('turn.completed')['seq'], 2)
        self.assertEqual([json.loads(line)['seq'] for line in log.path.read_bytes().splitlines()], [1, 2])

    def test_valid_final_line_without_newline_is_not_discarded(self):
        log = self.session.events
        log.append('turn.started', prompt='ok')
        record = log.append('message.delta', durable=False, text='complete')
        log.path.write_bytes(log.path.read_bytes().rstrip(b'\n'))
        restored = self.new_store().open(self.session.id).events
        self.assertEqual(restored.read()[-1], record)
        self.assertEqual(restored.append('turn.completed')['seq'], 3)
        self.assertEqual([json.loads(line)['seq'] for line in log.path.read_bytes().splitlines()], [1, 2, 3])

    def test_middle_corruption_and_invalid_complete_tail_are_rejected(self):
        log = self.session.events
        log.append('turn.started', prompt='ok')
        log.append('turn.completed')
        good = log.path.read_bytes()
        for damaged in (b'not json\n' + good, good + b'{oops}\n',
                        good + b'{"seq":9,"time":1,"type":"extra"}\n'):
            with self.subTest(damaged=damaged[-45:]):
                log.path.write_bytes(damaged)
                with self.assertRaisesRegex(ValueError, 'Corrupt|sequence'):
                    self.new_store()
                self.assertEqual(log.path.read_bytes(), damaged)

    def test_missing_journal_rejects_old_store_without_recreation(self):
        path = self.session.events.path
        path.unlink()
        with self.assertRaisesRegex(FileNotFoundError, 'migrat'):
            self.new_store()
        self.assertFalse(path.exists())

    def test_callback_sees_replayable_complete_event_and_summary_boundary(self):
        observed = []
        observer = self.store.open(self.session.id).events
        def callback(record):
            replay = observer.read(record['seq'] - 1)
            observed.append((record, replay, self.projected()[0]))
        log = self.store.open(self.session.id, callback).events
        log.append('message.delta', durable=False, text='partial')
        log.append('turn.started', prompt='boundary')
        self.assertEqual([(event['seq'], replay[0]['seq'], projected)
                          for event, replay, projected in observed], [(1, 1, 0), (2, 2, 2)])
        self.assertEqual([json.loads(line) for line in log.path.read_bytes().splitlines()], log.read())

    def test_serialization_failure_does_not_publish_or_consume_sequence(self):
        observed = []
        log = self.store.open(self.session.id, observed.append).events
        with self.assertRaises(TypeError):
            log.append('bad', value=object())
        with self.assertRaises(ValueError):
            log.append('bad', seq=10)
        self.assertEqual(observed, [])
        self.assertEqual(log.path.read_bytes(), b'')
        self.assertEqual(log.append('good')['seq'], 1)

    def test_projection_failure_after_journal_write_recovers_on_restart(self):
        log = self.session.events
        with self.store.database.connect(write=True) as db:
            db.execute('''CREATE TRIGGER reject_title BEFORE UPDATE OF auto_title ON sessions
                WHEN NEW.auto_title='recover' BEGIN SELECT RAISE(ABORT, 'projection failed'); END''')
        with self.assertRaises(sqlite3.IntegrityError):
            log.append('turn.started', prompt='recover')
        self.assertEqual([r['prompt'] for r in log.read()], ['recover'])
        self.assertEqual(self.projected()[0], 0)
        with self.store.database.connect(write=True) as db:
            db.execute('DROP TRIGGER reject_title')
        restored = self.new_store()
        self.assertEqual(self.projected(), (1, 'recover', 0, 'idle'))
        self.assertEqual(restored.open(self.session.id).events.append('turn.completed')['seq'], 2)


if __name__ == '__main__':
    unittest.main()

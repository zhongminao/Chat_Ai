import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from agent.core.session_runtime import SessionRuntimes, SessionBusy
from agent.model.messages import request_messages
from agent.model.protocol import ModelChunk, ToolCallDelta
from agent.workflow.config import load
from agent.workflow.history import HistoryNode
from agent.tools.executor import write_file
from agent.storage.event_log import EventLog


def calls(*items):
    return ModelChunk(tool_deltas=tuple(ToolCallDelta(index=index, id=f"call-{index}", name=name,
                      arguments=json.dumps(arguments)) for index, (name, arguments) in enumerate(items)))


def eventually(predicate, timeout=5):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for session state")


class SessionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = replace(load(), workspace=self.root, event_log=self.root / 'events.jsonl', mcp={}, max_rounds=4)
        self.registries = []
        self.releases = []
        self.client_patch = patch('agent.model.catalog.ModelCatalog.runtime', return_value=(object(), object()))
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)

    def tearDown(self):
        for event in self.releases:
            event.set()
        for registry in self.registries:
            for runtime in list(registry.items.values()):
                runtime.control.request_stop()
            for runtime in list(registry.items.values()):
                runtime.queue.join()
            for runtime in list(registry.items.values()):
                runtime.queue.put(None)
                runtime.worker.join(5)
        self.temp.cleanup()

    def registry(self):
        registry = SessionRuntimes(self.config)
        self.registries.append(registry)
        return registry

    def release(self):
        event = threading.Event()
        self.releases.append(event)
        return event

    def records(self, runtime, kind):
        return [e for e in runtime.session.events.read() if e['type'] == kind]

    def test_child_survives_chat_and_parent_stop_and_report_is_not_a_human_message(self):
        child_release = self.release()
        child_started = threading.Event()
        parent_started = threading.Event()
        child_tokens = []
        main_requests = []

        def stream(client, model, messages, schemas, **kwargs):
            token = kwargs['context'].cancellation
            if messages[0]['content'].startswith('child system'):
                child_tokens.append(token)
                child_started.set()
                self.assertNotIn('delegate', [s['function']['name'] for s in schemas])
                while not child_release.wait(0.01):
                    token.raise_if_cancelled()
                yield calls(('submit', {'content': '# Child report\n42'}))
                return
            main_requests.append(list(messages))
            text = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), '')
            if messages[-1]['role'] == 'tool':
                yield ModelChunk(content='Main reply finished; child still running.')
            elif text == 'spawn':
                yield calls(('delegate', {'system_prompt': 'child system', 'user_prompt': 'child task'}))
            elif text == 'hold':
                parent_started.set()
                while not token.is_cancelled():
                    time.sleep(0.01)
                token.raise_if_cancelled()
            else:
                yield ModelChunk(content='normal conversation')

        with patch('agent.core.agent_runtime.stream', side_effect=stream):
            registry = self.registry()
            parent = registry.create()
            parent.enqueue('spawn')
            eventually(lambda: child_started.is_set() and not parent.busy)
            child = next(rt for rt in registry.items.values() if rt.parent_session_id)
            self.assertTrue(child.busy)
            self.assertNotEqual(parent.agent.session_id, child.agent.session_id)
            self.assertIsNot(parent.control, child.control)
            self.assertIsNot(parent.agent.images, child.agent.images)
            parent.enqueue('chat')
            eventually(lambda: not parent.busy)
            self.assertTrue(child.busy)
            parent.enqueue('hold')
            self.assertTrue(parent_started.wait(5))
            self.assertTrue(parent.stop())
            eventually(lambda: not parent.busy)
            before = len(main_requests)
            self.assertFalse(child_tokens[0].is_cancelled())
            child_release.set()
            registry.wait()
            self.assertEqual(len(main_requests), before, 'stopped main must not auto-resume')
            reports = self.records(parent, 'report.received')
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0]['content'], '# Child report\n42')
            self.assertEqual(reports[0]['status'], 'submitted')
            parent.receive(child.result())
            registry.wait()
            self.assertEqual(len(self.records(parent, 'report.received')), 1)
            parent.enqueue('continue')
            registry.wait()
            self.assertEqual(len([m for m in parent.agent.messages if m['role'] == 'agent']), 1)
            replay = HistoryNode(parent.session.events.read()).messages()
            self.assertEqual([m for m in replay if m['role'] == 'agent'],
                             [m for m in parent.agent.messages if m['role'] == 'agent'])
            wire = request_messages(parent.agent.messages, parent.agent.images)
            self.assertNotIn('agent', [m['role'] for m in wire])
            self.assertTrue(any('Child agent observation' in str(m['content']) for m in wire))
            with self.assertRaises(ValueError):
                child.enqueue('resubmit')
            with self.assertRaises(SessionBusy):
                registry.delete(parent.session.id)

    def test_two_children_run_concurrently_submit_once_and_wake_idle_parent(self):
        release = self.release()
        entered = set()
        entered_lock = threading.Lock()
        marker = self.root / 'must-not-exist'

        def stream(client, model, messages, schemas, **kwargs):
            if messages[0]['content'].startswith('child-'):
                name = messages[0]['content'].splitlines()[0]
                with entered_lock:
                    entered.add(name)
                self.assertTrue(release.wait(5))
                yield calls(('submit', {'content': name}), ('submit', {'content': 'duplicate'}),
                            ('write_file', {'path': str(marker), 'content': 'bad'}))
            elif messages[-1]['role'] == 'user':
                yield calls(*[('delegate', {'system_prompt': f'child-{i}', 'user_prompt': 'work'}) for i in range(2)])
            else:
                yield ModelChunk(content='parent continues')

        with patch('agent.core.agent_runtime.stream', side_effect=stream):
            registry = self.registry()
            parent = registry.create()
            parent.enqueue('spawn')
            eventually(lambda: len(entered) == 2)
            self.assertEqual(sum(rt.busy for rt in registry.items.values() if rt.parent_session_id), 2)
            release.set()
            registry.wait()
            self.assertFalse(marker.exists())
            reports = self.records(parent, 'report.received')
            self.assertEqual({r['content'] for r in reports}, {'child-0', 'child-1'})
            self.assertEqual(len(reports), 2)
            self.assertEqual(len([e for e in self.records(parent, 'turn.started') if e.get('source') == 'agent_report']), 2)
            for child in [rt for rt in registry.items.values() if rt.parent_session_id]:
                self.assertEqual(len(self.records(child, 'report.submitted')), 1)
                # All calls have a tool result, including calls skipped after submit.
                wire = request_messages(HistoryNode(child.session.events.read()).messages(), child.agent.images)
                self.assertEqual(sum(m['role'] == 'tool' for m in wire), 3)

    def test_failure_missing_submit_and_child_cancellation_are_delivered(self):
        entered = threading.Event()

        def stream(client, model, messages, schemas, **kwargs):
            system = messages[0]['content']
            if system.startswith('crash'):
                raise RuntimeError('intentional failure')
            if system.startswith('missing'):
                yield ModelChunk(content='not a report')
            elif system.startswith('cancel'):
                entered.set()
                token = kwargs['context'].cancellation
                while not token.is_cancelled():
                    time.sleep(0.01)
                token.raise_if_cancelled()
            else:
                yield ModelChunk(content='received result')

        with patch('agent.core.agent_runtime.stream', side_effect=stream):
            registry = self.registry()
            parent = registry.create()
            for name in ['crash', 'missing', 'cancel']:
                identifier = json.loads(parent.delegate(name, 'work'))['session_id']
                child = registry.get(identifier)
                if name == 'cancel':
                    self.assertTrue(entered.wait(5))
                    child.stop()
                registry.wait()
            reports = self.records(parent, 'report.received')
            self.assertEqual([r['status'] for r in reports], ['failed', 'failed', 'cancelled'])
            self.assertIn('without calling submit', reports[1]['content'])

    def test_main_submit_is_optional_and_only_ends_one_execution(self):
        def stream(client, model, messages, schemas, **kwargs):
            if messages[-1]['content'] == 'formal':
                yield calls(('submit', {'content': '**Final report**'}))
            else:
                yield ModelChunk(content='hello again')
        with patch('agent.core.agent_runtime.stream', side_effect=stream):
            registry = self.registry()
            parent = registry.create()
            parent.enqueue('formal')
            registry.wait()
            self.assertEqual(len(self.records(parent, 'report.submitted')), 1)
            parent.enqueue('chat')
            registry.wait()
            self.assertIsNone(parent.agent.submitted_report)
            self.assertEqual(self.records(parent, 'turn.completed')[-1]['answer'], 'hello again')

    def test_restart_recovers_reports_once_and_does_not_rerun_unfinished_children(self):
        def stream(*args, **kwargs):
            yield ModelChunk(content='received')
        with patch('agent.core.agent_runtime.stream', side_effect=stream):
            registry = self.registry()
            parent = registry.create()
            completed = registry.store.create(parent_session_id=parent.session.id, system_prompt='done')
            completed.events.append('report.submitted', content='saved report')
            interrupted = registry.store.create(parent_session_id=parent.session.id, system_prompt='interrupted')
            interrupted.events.append('turn.started', prompt='unfinished')
            restored_registry = self.registry()
            restored = restored_registry.get(parent.session.id)
            restored_registry.wait()
            reports = self.records(restored, 'report.received')
            self.assertEqual({r['status'] for r in reports}, {'submitted', 'failed'})
            self.assertEqual(len(restored_registry.items), 1)
            again_registry = self.registry()
            again = again_registry.get(parent.session.id)
            again_registry.wait()
            self.assertEqual(len(self.records(again, 'report.received')), 2)

    def test_concurrent_file_writes_use_separate_atomic_temporary_files(self):
        barrier = threading.Barrier(2)
        original = Path.replace
        def replace_file(path, target):
            barrier.wait(timeout=5)
            return original(path, target)
        with patch.object(Path, 'replace', replace_file), ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(write_file, self.root, 'shared.txt', text) for text in ['first', 'second']]
            for future in futures:
                future.result(timeout=5)
        self.assertIn((self.root / 'shared.txt').read_text(), ['first', 'second'])
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_event_reader_ignores_an_incomplete_last_line_during_append(self):
        log = EventLog(self.root / 'events.jsonl')
        log.append('complete')
        with log.path.open('a') as file:
            file.write('{"seq": 2, "type": "partial')
        self.assertEqual([e['type'] for e in log.read()], ['complete'])


if __name__ == '__main__':
    unittest.main()

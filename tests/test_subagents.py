import json
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from agent.core.session_registry import SessionRegistry
from agent.model.request_messages import request_messages
from agent.model.protocol import ModelChunk, ToolCallDelta
from agent.web.images import image_router
from agent.workflow.config import load
from agent.workflow.message_replay import restore_display_messages


def calls(*items):
    return ModelChunk(tool_deltas=tuple(ToolCallDelta(index=i, id=f'call-{i}', name=name,
                      arguments=json.dumps(args)) for i, (name, args) in enumerate(items)))


def eventually(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('timed out')


class SubagentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = replace(load(), approval_mode="full_access", workspace=self.root, storage_dir=self.root, mcp={}, max_rounds=12)
        self.registry = SessionRegistry(self.config)
        self.releases = []
        self.clients = patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object()))
        self.clients.start()

    def tearDown(self):
        for event in self.releases:
            event.set()
        for runtime in list(self.registry.items.values()):
            runtime.stop()
        self.registry.wait()
        for runtime in list(self.registry.items.values()):
            runtime.queue.put(None)
            runtime.worker.join(5)
        self.clients.stop()
        self.temp.cleanup()

    def test_concurrent_children_no_auto_resume_watch_wait_stop_next_turn_and_images(self):
        image_path = self.root / 'four views.png'
        Image.new('RGB', (40, 30), 'blue').save(image_path)
        release = threading.Event()
        self.releases.append(release)
        entered = set()
        tokens = []
        main_requests = []
        parent = self.registry.create()

        def stream(client, model, messages, schemas, **kwargs):
            if messages[1]['content'].startswith('child-'):
                entered.add(messages[1]['content'])
                tokens.append(kwargs['context'].cancellation)
                self.assertNotIn('delegate', [s['function']['name'] for s in schemas])
                while not release.wait(0.01):
                    kwargs['context'].cancellation.raise_if_cancelled()
                yield calls(('show_image', {'path': str(image_path)}), ('submit', {'content': '# Result\n42'}))
                return
            main_requests.append(list(messages))
            prompt = next(m['content'] for m in reversed(messages) if m['role'] == 'user')
            last = messages[-1]
            if last['role'] == 'tool':
                if last.get('tool_call_id') == 'read-report':
                    yield calls(('submit', {'content': last['content']}))
                elif prompt == 'next' and 'changes' in last['content']:
                    path = json.loads(last['content'])['changes'][0]['result_path']
                    yield ModelChunk(tool_deltas=(ToolCallDelta(id='read-report', name='read_file', arguments=json.dumps({'path': path})),))
                else:
                    yield ModelChunk(content='Main finished its reply.')
            elif prompt == 'spawn':
                yield calls(*[('delegate', {'user_prompt': f'child-{i}'}) for i in range(2)])
            elif prompt == 'wait':
                cursor = self.registry.monitor(parent.session.id).watch()['cursor']
                yield calls(('watch', {'cursor': cursor, 'timeout': 120}))
            elif prompt == 'next':
                yield calls(('watch', {}))
            else:
                yield ModelChunk(content='normal chat')

        with patch('agent.core.agent_runtime.stream', side_effect=stream):
            parent.enqueue('spawn')
            eventually(lambda: len(entered) == 2 and not parent.busy)
            children = [rt for rt in self.registry.items.values() if rt.parent_session_id]
            self.assertTrue(all(child.busy for child in children))
            for child in children:
                self.assertIsNot(child.agent.state, parent.agent.state)
                self.assertIsNot(child.agent.state['messages'], parent.agent.state['messages'])
                self.assertEqual(json.loads(json.dumps(child.agent.state))['execution']['status'], 'running')
            self.assertIsNot(parent.control, children[0].control)
            parent.enqueue('chat')
            eventually(lambda: not parent.busy)
            parent.enqueue('wait')
            eventually(lambda: any(e['type'] == 'tool.requested' and e['tool'] == 'watch' for e in parent.session.events.read()))
            parent.stop()
            eventually(lambda: not parent.busy)
            self.assertTrue(all(not token.is_cancelled() for token in tokens))
            count = len(main_requests)
            release.set()
            self.registry.wait()
            self.assertEqual(len(main_requests), count, 'completion must not invoke the parent model')
            states = self.registry.monitor(parent.session.id).watch()['changes']
            self.assertEqual(len(states), 2)
            self.assertTrue(all(s['status'] == 'completed' for s in states))
            self.assertTrue(all(json.loads(json.dumps(child.agent.state))['execution']['status'] == 'completed'
                                for child in children))
            self.assertTrue(all('result' not in s and Path(s['result_path']).is_file() for s in states))
            self.assertFalse(any(e['type'] == 'report.received' for e in parent.session.events.read()))
            parent.enqueue('next')
            self.registry.wait()
            report_content = parent.agent.state['execution']['report']
            self.assertTrue(report_content)
            self.assertIn('/api/sessions/', report_content)
            self.assertNotIn('](' + str(image_path), report_content)
            report = Path(states[0]['result_path']).read_text()
            child_id = states[0]['session_id']
            image = self.registry.store.open(child_id).images.list()[0]
            url = f'/api/sessions/{child_id}/images/{image["id"]}/content'
            self.assertIn(f']({url})', report)
            self.assertIn('<!-- image_file:', report)
            self.assertEqual(sum('](' + url + ')' in line for line in report.splitlines()), 1)
            api = FastAPI()
            api.include_router(image_router(self.registry.store))
            with TestClient(api) as client:
                response = client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.headers['content-type'].startswith('image/png'))
            history = restore_display_messages(parent.session.events.read())
            self.assertNotIn('agent', [m['role'] for m in history])
            self.assertEqual([m['role'] for m in history], [m['role'] for m in parent.agent.state['messages'][1:]])
            request_messages(history, parent.agent.images)
            self.assertTrue(any(e['type'] == 'turn.cancelled' for e in parent.session.events.read()))
            with self.assertRaises(ValueError):
                children[0].enqueue('again')
            self.registry.delete(parent.session.id)
            for runtime in [parent, *children]:
                runtime.worker.join(5)
                self.assertFalse(runtime.worker.is_alive())
            self.assertFalse(self.registry.store.children(parent.session.id))
            self.assertTrue(all(not Path(state['result_path']).exists() for state in states))

    def test_failures_missing_submit_cancellation_and_restart_are_status_only(self):
        entered = threading.Event()
        parent = self.registry.create()
        def stream(client, model, messages, schemas, **kwargs):
            prompt = messages[1]['content']
            if prompt.startswith('crash'):
                raise RuntimeError('intentional crash')
            if prompt.startswith('cancel'):
                entered.set()
                token = kwargs['context'].cancellation
                while not token.is_cancelled():
                    time.sleep(0.01)
                token.raise_if_cancelled()
            yield ModelChunk(content='ordinary text without submit')
        with patch('agent.core.agent_runtime.stream', side_effect=stream):
            for name in ['crash', 'missing', 'cancel']:
                receipt = json.loads(self.registry.delegate(parent.session.id, name))
                self.assertIn('watch', receipt['hint'])
                child = self.registry.get(receipt['session_id'])
                if name == 'cancel':
                    self.assertTrue(entered.wait(5))
                    child.stop()
                self.registry.wait()
        states = self.registry.monitor(parent.session.id).watch()['changes']
        self.assertEqual([s['status'] for s in states], ['failed', 'failed', 'cancelled'])
        executions = [json.loads(json.dumps(self.registry.get(s['session_id']).agent.state))['execution']
                      for s in states]
        self.assertEqual([execution['status'] for execution in executions], ['failed', 'failed', 'cancelled'])
        self.assertIn('intentional crash', executions[0]['error'])
        self.assertIn('without calling submit', executions[1]['error'])
        self.assertEqual(parent.session.events.read()[0]['type'], 'agent.created')
        self.assertFalse(any(e['type'] == 'turn.started' for e in parent.session.events.read()))
        interrupted = self.registry.store.create(parent_session_id=parent.session.id, title='interrupted')
        restored = SessionRegistry(self.config)
        states = restored.monitor(parent.session.id).watch()['changes']
        self.assertEqual(states[-1]['session_id'], interrupted.id)
        self.assertEqual(states[-1]['status'], 'failed')
        self.assertEqual(restored.items, {}, 'reading the monitor must not start sessions or models')

    def test_configured_child_role_retry_and_history_without_false_completion(self):
        self.registry.config = replace(self.config, system_prompt='main {workspace}',
                                       child_system_prompt='child instructions {workspace}')
        parent = self.registry.create()
        self.assertEqual(parent.state['role'], 'main')
        self.assertTrue(parent.state['messages'][0]['content'].startswith('main '))
        self.assertIn('delegate', [s['function']['name'] for s in parent.agent.tools.schemas])
        child = self.registry.create(parent_session_id=parent.session.id, system_prompt='legacy override')
        observed = []

        def stream(client, model, messages, schemas, **kwargs):
            observed.append(list(messages))
            self.assertEqual(messages[0]['content'], f'child instructions {self.root}')
            self.assertNotIn('delegate', [s['function']['name'] for s in schemas])
            self.assertIn('watch', [s['function']['name'] for s in schemas])
            if len(observed) == 1:
                yield ModelChunk(content='Finished work, but forgot to submit.')
            else:
                self.assertEqual(messages[-1]['role'], 'system')
                yield calls(('submit', {'content': '# Submitted after reminder'}))

        with patch('agent.core.agent_runtime.stream', side_effect=stream):
            child.start('work')
            self.registry.wait()
        events = child.session.events.read()
        self.assertEqual(child.state['role'], 'child')
        self.assertEqual(child.state['execution']['completion_reminders'], 1)
        self.assertEqual(child.state['execution']['status'], 'completed')
        for kind in ['turn.started', 'completion.reminded', 'report.submitted', 'turn.completed']:
            self.assertEqual(sum(e['type'] == kind for e in events), 1)
        self.assertFalse(any(e['type'] == 'turn.failed' for e in events))
        history = [{k: v for k, v in m.items() if k != 'name'} for m in restore_display_messages(events)]
        self.assertEqual(child.state['messages'][1:], history)
        self.assertEqual(len([m for m in history if m['role'] == 'user']), 1)

    def test_missing_submit_has_one_reminder_and_obeys_total_round_budget(self):
        for budget, expected_calls, reminders in [(12, 2, 1), (1, 1, 0)]:
            self.registry.config = replace(self.config, max_rounds=budget)
            parent = self.registry.create()
            with patch('agent.core.agent_runtime.stream', side_effect=lambda *a, **k: iter([ModelChunk(content='draft')])) as model:
                receipt = json.loads(self.registry.delegate(parent.session.id, 'work'))
                self.registry.wait()
            child = self.registry.get(receipt['session_id'])
            events = child.session.events.read()
            self.assertEqual(model.call_count, expected_calls)
            self.assertEqual(child.state['execution']['completion_reminders'], reminders)
            self.assertEqual(sum(e['type'] == 'turn.failed' for e in events), 1)
            self.assertFalse(any(e['type'] == 'turn.completed' for e in events))
            self.assertEqual(self.registry.monitor(parent.session.id).watch()['changes'][0]['status'], 'failed')

    def test_delegate_only_accepts_task_and_does_not_store_custom_system_prompt(self):
        parent = self.registry.create()
        schema = next(s['function'] for s in parent.agent.tools.schemas if s['function']['name'] == 'delegate')
        self.assertEqual(schema['parameters']['required'], ['user_prompt'])
        self.assertEqual(set(schema['parameters']['properties']), {'user_prompt'})
        with patch('agent.core.agent_runtime.stream', side_effect=lambda *a, **k: iter([calls(('submit', {'content': 'done'}))])):
            receipt = json.loads(self.registry.delegate(parent.session.id, 'complete task context'))
            self.registry.wait()
        child = self.registry.get(receipt['session_id'])
        self.assertNotIn('system_prompt', child.meta)
        self.assertEqual(child.state['messages'][1]['content'], 'complete task context')
        count = len(self.registry.items)
        result = parent.agent.tools.call('delegate', {'system_prompt': 'override', 'user_prompt': 'work'})
        self.assertIn('[tool error]', result)
        self.assertEqual(len(self.registry.items), count)

    def test_report_rewrites_local_image_paths_without_duplicating_images(self):
        session = self.registry.store.create()
        image_path = self.root / 'image.png'
        Image.new('RGB', (20, 20)).save(image_path)
        store = session.images
        image = store.add_file(image_path)
        session.events.append('tool.requested', runId='run', callId='show', arguments={'path': str(image_path)})
        session.events.append('tool.completed', runId='run', callId='show', images=[image])
        from agent.storage.reports import save
        path, content = save(session, 'run', f'![plot]({image_path})', self.root)
        self.assertIn(f']({store.url(image)})', content)
        self.assertEqual(content.count(']('), 1)
        self.assertEqual(path.read_text().strip(), content)


if __name__ == '__main__':
    unittest.main()

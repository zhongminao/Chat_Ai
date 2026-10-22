import copy
import io
import json
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack, redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.core.session_registry import SessionRegistry
from agent.core.steering import InputDelivery
from agent.model.protocol import ModelChunk, ToolCallDelta
from agent.web import app as web
from agent.workflow.config import load
from agent.workflow.context_compaction import plan
from agent.workflow.input import UserInput
from agent.workflow.message_replay import restore_model_messages, restore_display_messages


class SteeringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.registry = SessionRegistry(replace(load(), storage_dir=self.root / 'storage', workspace=self.root,
            mcp={}, context={'enabled': False}, approval_mode='full_access', max_rounds=5))
        self.main = self.registry.create()
        self.entered, self.release = threading.Event(), threading.Event()
        self.requests = []
        self.addCleanup(self.close)

    def close(self):
        self.release.set()
        for rt in self.registry.items.values(): rt.stop()
        self.registry.wait()
        for rt in self.registry.items.values():
            rt.queue.put(None)
            rt.worker.join(3)
        self.temp.cleanup()

    def stream(self, client, model, messages, *args, **kwargs):
        self.requests.append(copy.deepcopy(messages))
        if len(self.requests) == 1:
            yield ModelChunk(content='reading', tool_deltas=tuple(
                ToolCallDelta(i, str(i), 'read_file', json.dumps({'path': f'file-{i}'})) for i in range(2)), finish_reason='tool_calls')
        else:
            yield ModelChunk(content='guided answer', finish_reason='stop')

    def tool(self, root, name, arguments, context):
        if arguments['path'] == 'file-0':
            self.entered.set()
            while not self.release.wait(.01): context.cancellation.raise_if_cancelled()
        return 'actual result ' + arguments['path']

    def patched(self, stream=None):
        stack = ExitStack()
        stack.enter_context(patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())))
        stack.enter_context(patch('agent.core.agent_runtime.stream', side_effect=stream or self.stream))
        stack.enter_context(patch('agent.tools.router.execute', side_effect=self.tool))
        return stack

    def test_web_guidance_waits_for_whole_tool_batch_and_replays_exact_context(self):
        with self.patched(), patch.object(web, 'registry', self.registry), patch.object(web, 'session_store', self.registry.store), TestClient(web.app) as client:
            path = f'/api/sessions/{self.main.session.id}'
            self.main.enqueue('initial request')
            self.assertTrue(self.entered.wait(3))
            data = {'message_id': 'guide-one', 'content': 'use official sources'}
            self.assertEqual(client.post(path + '/guidance', json=data).status_code, 200)
            self.assertEqual(client.post(path + '/guidance', json=data).status_code, 200)
            self.assertEqual(client.post(path + '/guidance', json={**data, 'content': 'changed'}).status_code, 400)
            self.main.send('also verify dates', 'guide-two')
            self.assertEqual(len(self.requests), 1)
            self.assertNotIn('use official sources', [m.get('content') for m in self.main.state['messages']])
            self.release.set()
            self.registry.wait()
            messages = self.requests[1]
            self.assertEqual([m['role'] for m in messages[-5:]], ['assistant', 'tool', 'tool', 'user', 'user'])
            self.assertEqual([m['content'] for m in messages[-4:]], ['actual result file-0', 'actual result file-1', 'use official sources', 'also verify dates'])
            records = self.main.session.events.read()
            self.assertEqual(sum(e['type'] == 'guidance.queued' for e in records), 2)
            self.assertEqual(sum(e['type'] == 'turn.started' for e in records), 1)
            self.assertLess(max(e['seq'] for e in records if e['type'] == 'tool.completed'),
                            min(e['seq'] for e in records if e['type'] == 'guidance.applied'))
            self.assertEqual(restore_model_messages(records, self.main.state['messages'][0]), self.main.state['messages'])

    def test_stop_leaves_accepted_guidance_undelivered_and_not_in_model_history(self):
        with self.patched():
            self.main.enqueue('initial')
            self.assertTrue(self.entered.wait(3))
            self.main.send('must not execute', 'stop-guide')
            self.main.stop()
            self.registry.wait()
            records = self.main.session.events.read()
            self.assertTrue(any(e['type'] == 'guidance.undelivered' for e in records))
            self.assertFalse(any(e['type'] == 'guidance.applied' for e in records))
            self.assertFalse(any(m.get('content') == 'must not execute' for m in restore_model_messages(records, self.main.state['messages'][0])))
            reopened = SessionRegistry(self.registry.config).get(self.main.session.id)
            try:
                self.assertEqual(reopened.steering.pending, [])
                self.assertFalse(reopened.busy)
            finally:
                reopened.queue.put(None)
                reopened.worker.join(3)

    def test_guidance_does_not_bypass_a_pending_tool_approval(self):
        self.main.approvals.set_mode('audit')
        def stream(client, model, messages, *args, **kwargs):
            self.requests.append(copy.deepcopy(messages))
            if len(self.requests) == 1:
                yield ModelChunk(tool_deltas=(ToolCallDelta(0, 'bash', 'run_bash', '{"command":"echo test"}'),), finish_reason='tool_calls')
            else:
                yield ModelChunk(content='continued', finish_reason='stop')
        with self.patched(stream):
            self.main.enqueue('initial')
            deadline = time.monotonic() + 3
            while not self.main.approvals.snapshot()['pending']:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.01)
            self.main.send('continue without this tool', 'approval-guide')
            self.assertEqual(len(self.requests), 1)
            self.assertFalse(any(e['type'] == 'guidance.applied' for e in self.main.session.events.read()))
            self.main.approvals.resolve(self.main.approvals.snapshot()['pending'][0]['id'], False)
            self.registry.wait()
            self.assertTrue(self.requests[1][-2]['content'].startswith('[tool denied]'))
            self.assertEqual(self.requests[1][-1]['content'], 'continue without this tool')

    def test_guidance_before_plain_final_answer_or_submit_prevents_premature_finish(self):
        for submit in [False, True]:
            with self.subTest(submit=submit):
                rt = self.registry.create()
                entered, release = threading.Event(), threading.Event()
                requests = []
                def stream(client, model, messages, *args, **kwargs):
                    requests.append(copy.deepcopy(messages))
                    if len(requests) == 1:
                        entered.set()
                        self.assertTrue(release.wait(3))
                    text = 'old' if len(requests) == 1 else 'revised'
                    if submit:
                        yield ModelChunk(tool_deltas=(ToolCallDelta(0, text, 'submit', json.dumps({'content': text})),), finish_reason='tool_calls')
                    else:
                        yield ModelChunk(content=text, finish_reason='stop')
                with self.patched(stream):
                    rt.enqueue('initial')
                    self.assertTrue(entered.wait(3))
                    rt.send('revise this', 'revision')
                    release.set()
                    self.registry.wait()
                    self.assertEqual(rt.state['execution']['answer'], 'revised')
                    records = rt.session.events.read()
                    self.assertEqual(sum(e['type'] == 'turn.completed' for e in records), 1)
                    if submit:
                        self.assertEqual([e['content'] for e in records if e['type'] == 'report.submitted'], ['revised'])

    def test_finalization_closes_acceptance_atomically_and_sent_content_is_immutable(self):
        records = []
        queue = InputDelivery(threading.RLock(), lambda typ, **e: records.append({'type': typ, **e}), [])
        queue.begin()
        queue.add('a', UserInput('original'), [])
        self.assertEqual(queue.take('run', finish=True), [{'role': 'user', 'content': 'original'}])
        self.assertTrue(queue.accepting)
        self.assertEqual(queue.take('run', finish=True), [])
        self.assertFalse(queue.accepting)
        with self.assertRaises(ValueError): queue.add('b', UserInput('too late'), [])
        with self.assertRaises(ValueError): queue.add('a', UserInput('edited'), [])
        queue.add('a', UserInput('original'), [])
        self.assertEqual(len(records), 2)

    def test_compaction_retains_all_new_guidance_and_last_complete_tool_group(self):
        messages = [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': 'old task'},
                    {'role': 'assistant', 'content': 'old answer'}, {'role': 'user', 'content': 'new task'},
                    {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'call'}]},
                    {'role': 'tool', 'tool_call_id': 'call', 'content': 'actual tool result'},
                    {'role': 'user', 'content': 'guide one'}, {'role': 'user', 'content': 'guide two'}]
        selected = plan({'messages': messages}, 10, {'enabled': True, 'trigger_tokens': 5})
        self.assertEqual(selected['retained'], messages[4:])

    def test_mail_and_guidance_share_one_safe_batch_without_exposing_bodies(self):
        child = self.registry.create(parent_session_id=self.main.session.id)
        with self.patched():
            self.main.enqueue('initial request')
            self.assertTrue(self.entered.wait(3))
            self.main.send('user revision', 'guide')
            ids = [self.registry.notify_agent(child.session.id, self.main.session.id, body, kind='feedback')['id']
                   for body in ('private body one', 'private body two')]
            self.release.set()
            self.registry.wait()
        self.assertEqual(len(self.requests), 2)
        messages = self.requests[1]
        self.assertEqual([m['role'] for m in messages[-4:]], ['tool', 'tool', 'user', 'system'])
        self.assertEqual(messages[-2]['content'], 'user revision')
        for identifier in ids:
            self.assertIn(identifier, messages[-1]['content'])
        self.assertNotIn('private body', str(messages))
        self.assertEqual(self.registry.mailbox_unread_count(self.main.session.id), 2)
        events = self.main.session.events.read()
        self.assertEqual(sum(e['type'] == 'mailbox.notified' for e in events), 1)
        display = restore_display_messages(events)
        self.assertFalse(any(message['role'] == 'system' for message in display))
        self.assertFalse(any(identifier in str(display) for identifier in ids))
        self.assertEqual(restore_model_messages(events, messages[0]), self.main.state['messages'])

    def test_child_receives_parent_mail_without_polling_and_seals_submission(self):
        child = self.registry.create(parent_session_id=self.main.session.id)
        def stream(client, model, messages, *args, **kwargs):
            self.requests.append(copy.deepcopy(messages))
            if len(self.requests) == 1:
                self.entered.set()
                self.assertTrue(self.release.wait(3))
            yield ModelChunk(tool_deltas=(ToolCallDelta(
                0, str(len(self.requests)), 'submit', json.dumps({'content': 'done'})),), finish_reason='tool_calls')
        with self.patched(stream):
            child.start(UserInput('child task'))
            self.assertTrue(self.entered.wait(3))
            identifier = self.registry.notify_agent(self.main.session.id, child.session.id, 'parent direction')['id']
            self.release.set()
            self.registry.wait()
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.requests[1][-1]['role'], 'system')
        self.assertIn(identifier, self.requests[1][-1]['content'])
        self.assertEqual(self.registry.mailbox_unread_count(child.session.id), 1)
        with self.assertRaises(ValueError):
            self.registry.notify_agent(self.main.session.id, child.session.id, 'too late')

    def test_mail_blocks_submission_once_and_restores_deduplication(self):
        records, mail = [], [{'id': 'first'}]
        emit = lambda typ, **fields: records.append({'type': typ, **fields})
        delivery = InputDelivery(threading.RLock(), emit, [], inbox=lambda: mail)
        delivery.begin()
        delivery.add('guide', UserInput('revision'), [])
        batch = delivery.take('run', finish=True)
        self.assertEqual([m['role'] for m in batch], ['user', 'system'])
        self.assertTrue(delivery.accepting)
        # Arrival after the first batch is delivered at the next boundary.
        mail.append({'id': 'second'})
        self.assertIn('second', delivery.take('run', finish=True)[0]['content'])
        self.assertEqual(delivery.take('run', finish=True), [])
        self.assertFalse(delivery.accepting)
        restored = InputDelivery(threading.RLock(), emit, records, inbox=lambda: mail)
        restored.begin()
        self.assertEqual(restored.take('next'), [])

    def test_new_mail_invalidates_candidate_submit_without_watch(self):
        child = self.registry.create(parent_session_id=self.main.session.id)
        def stream(client, model, messages, *args, **kwargs):
            self.requests.append(copy.deepcopy(messages))
            if len(self.requests) == 1:
                self.entered.set()
                self.assertTrue(self.release.wait(3))
            answer = 'old' if len(self.requests) == 1 else 'revised'
            yield ModelChunk(tool_deltas=(ToolCallDelta(
                0, answer, 'submit', json.dumps({'content': answer})),), finish_reason='tool_calls')
        with self.patched(stream):
            self.main.enqueue('initial')
            self.assertTrue(self.entered.wait(3))
            identifier = self.registry.notify_agent(child.session.id, self.main.session.id, 'change plan', kind='feedback')['id']
            self.release.set()
            self.registry.wait()
        self.assertEqual(len(self.requests), 2)
        self.assertIn(identifier, self.requests[1][-1]['content'])
        self.assertEqual([e['content'] for e in self.main.session.events.read()
                          if e['type'] == 'report.submitted'], ['revised'])

    def test_cli_reads_guidance_while_execution_is_running(self):
        from agent.cli.main import main
        prompts = iter(['initial', 'live guidance', '/exit'])
        owner = threading.get_ident()
        def prompt(*args):
            self.assertEqual(threading.get_ident(), owner)
            value = next(prompts)
            if value == 'live guidance': self.assertTrue(self.entered.wait(3))
            if value == '/exit':
                self.release.set()
                self.registry.wait()
            return value
        with self.patched(), patch('sys.argv', ['chat_ai', '--session', self.main.session.id]), \
             patch('agent.cli.main.SessionRegistry', return_value=self.registry), \
             patch('agent.cli.main.PromptSession', return_value=SimpleNamespace(prompt=prompt)), redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(self.requests[1][-1]['content'], 'live guidance')

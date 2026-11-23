import json
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.agentsessionstate.config import load
from agent.agentsessionstate.message_replay import restore_model_messages
from agent.core.cancellation import CancellationToken, ExecutionContext, RunCancelled
from agent.core.session_registry import SessionRegistry
from agent.model.protocol import ModelChunk, ToolCallDelta
from agent.storage.session import SessionStore
from agent.tools.approval import requires_approval
from agent.tools.questions import QuestionGate, QuestionConflict, QuestionNotFound
from agent.tools.router import ToolRouter
from agent.tools.schema import ASK_USER_SCHEMA, TOOL_SCHEMAS
from agent.web import app as web


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError('condition did not become true')
        time.sleep(.005)


def options(count=3):
    return [{'title': f'方向 {i} — 任意标题', 'description': f'完整说明 {i}\n细节，不是选项 ID'}
            for i in range(count)]


class QuestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.events = SessionStore(self.root).create().events
        self.gate = QuestionGate(self.events.append)
        self.context = ExecutionContext(CancellationToken())
        self.router = ToolRouter(self.root, ask_user=self.gate.request)

    def start_call(self, arguments):
        result = []
        def run():
            try:
                result.append(self.router.call('ask_user', arguments, self.context,
                                               run_id='run', call_id='call'))
            except BaseException as exc:
                result.append(exc)
        thread = threading.Thread(target=run)
        thread.start()
        self.addCleanup(thread.join, 3)
        self.addCleanup(self.context.cancellation.cancel)
        wait_until(lambda: self.gate.snapshot()['pending'])
        return thread, result, self.gate.snapshot()['pending'][0]

    def test_schema_is_runtime_only_and_not_an_approval(self):
        self.assertNotIn('ask_user', [s['function']['name'] for s in TOOL_SCHEMAS])
        self.assertNotIn('ask_user', [s['function']['name'] for s in ToolRouter(self.root).schemas])
        self.assertIn('ask_user', [s['function']['name'] for s in self.router.schemas])
        self.assertFalse(requires_approval('ask_user', False))
        parameters = ASK_USER_SCHEMA['function']['parameters']
        self.assertEqual(parameters['required'], ['question'])
        self.assertFalse(parameters['additionalProperties'])
        option = parameters['properties']['options']['items']
        self.assertEqual(set(option['properties']), {'title', 'description'})
        self.assertFalse(option['additionalProperties'])

    def test_json_schema_accepts_same_options_and_rejects_invalid_inputs(self):
        from jsonschema import Draft202012Validator
        validator = Draft202012Validator(ASK_USER_SCHEMA['function']['parameters'])
        valid = [{'question': 'q'}, {'question': 'q', 'options': []}]
        valid += [{'question': 'q', 'options': options(n)} for n in range(2, 6)]
        for args in valid:
            with self.subTest(args=args):
                self.assertTrue(validator.is_valid(args))
        invalid = [{'question': ' '}, {'question': 'x' * 2001}, {'question': 'q', 'options': None},
                   {'question': 'q', 'options': options(1)}, {'question': 'q', 'options': options(6)},
                   {'question': 'q', 'options': [{'title': ' ', 'description': 'd'}] * 2},
                   {'question': 'q', 'options': [{'title': 't', 'description': 'd', 'id': 'x'}] * 2}]
        for args in invalid:
            with self.subTest(args=args):
                self.assertFalse(validator.is_valid(args))

    def test_two_to_five_arbitrary_options_result_and_event_are_full(self):
        for count in range(2, 6):
            with self.subTest(count=count):
                choices = options(count)
                thread, result, item = self.start_call({'question': '请选择方向？', 'options': choices})
                self.assertEqual(item['options'], choices)
                self.assertEqual(item['callId'], 'call')
                self.assertEqual(item['runId'], 'run')
                snapshot = self.gate.snapshot()
                snapshot['pending'][0]['options'][0]['title'] = 'mutated snapshot'
                answer = self.gate.answer(item['questionId'], option_index=count - 1, text='ignored model/client text')
                thread.join(3)
                self.assertFalse(thread.is_alive())
                full = choices[-1]['title'] + '\n' + choices[-1]['description']
                self.assertEqual(answer, {'accepted': True, 'answer': {'option_index': count - 1, 'text': full}})
                tool_result = json.loads(result[0])
                self.assertEqual(tool_result['text'], full)
                self.assertEqual(tool_result['title'], choices[-1]['title'])
                self.assertEqual(tool_result['description'], choices[-1]['description'])
                self.assertEqual(tool_result['option_index'], count - 1)
                event = self.events.read()[-1]
                self.assertEqual(event['type'], 'question.answered')
                self.assertEqual(event['answer'], answer['answer'])
                self.assertEqual(self.gate.snapshot(), {'pending': []})

    def test_open_ended_absent_and_explicit_empty_and_custom_on_choice(self):
        for kwargs in ({}, {'options': []}, {'options': options()}):
            with self.subTest(kwargs=kwargs):
                thread, result, item = self.start_call({'question': 'Which?', **kwargs})
                response = self.gate.answer(item['questionId'], text='  自定义完整答案  ')
                thread.join(3)
                self.assertEqual(response['answer'], {'option_index': None, 'text': '自定义完整答案'})
                self.assertEqual(json.loads(result[0])['option_index'], None)
                self.assertNotIn('title', json.loads(result[0]))
                self.assertEqual(item['options'], kwargs.get('options', []))

    def test_invalid_tool_arguments_return_usual_errors_without_question(self):
        bad = [ {'question': value} for value in ('', ' \n', 3, None, 'x' * 2001)]
        bad += [{'question': 'q', 'options': value} for value in
                (None, {}, [options()[0]], options(6), [{'title': 't'}] * 2,
                 [{'title': ' ', 'description': 'd'}] * 2,
                 [{'title': 't', 'description': ''}] * 2,
                 [{'title': 'x' * 201, 'description': 'd'}] * 2,
                 [{'title': 't', 'description': 'x' * 1001}] * 2,
                 [{**options()[0], 'id': 'model_id'}] * 2)]
        bad += [{'question': 'q', 'unknown': True}]
        for args in bad:
            with self.subTest(args=str(args)[:100]):
                result = self.router.call('ask_user', args, self.context)
                self.assertTrue(result.startswith('[tool error]'), result)
        self.assertEqual(self.events.read(), [])
        self.assertEqual(self.gate.snapshot(), {'pending': []})

    def test_invalid_answers_leave_pending_then_idempotent_retry_and_conflict(self):
        thread, result, item = self.start_call({'question': 'q', 'options': options()})
        identifier = item['questionId']
        for answer in ({}, {'text': ''}, {'text': ' \n'}, {'text': 'x' * 4001},
                       {'text': 1}, {'option_index': -1}, {'option_index': 3},
                       {'option_index': True}, {'option_index': 1.0}, {'option_index': '1'}):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                self.gate.answer(identifier, **answer)
        self.assertEqual(len(self.gate.snapshot()['pending']), 1)
        accepted = self.gate.answer(identifier, option_index=0)
        thread.join(3)
        self.assertEqual(self.gate.answer(identifier, option_index=0), accepted)
        self.assertEqual(self.gate.answer(identifier, option_index=0, text='ignored'), accepted)
        with self.assertRaises(QuestionConflict):
            self.gate.answer(identifier, option_index=1)
        with self.assertRaises(QuestionConflict):
            self.gate.answer(identifier, text='a different answer')
        self.assertEqual(len([e for e in self.events.read() if e['type'] == 'question.answered']), 1)
        with self.assertRaises(QuestionNotFound):
            self.gate.answer('missing', text='answer')

    def test_immediate_subscriber_answer_has_no_lost_wakeup(self):
        def emit(kind, **data):
            self.events.append(kind, **data)
            if kind == 'question.requested':
                self.gate.answer(data['questionId'], text='immediate answer')
        self.gate = QuestionGate(emit)
        result = self.gate.request('q', context=self.context, run_id='r', call_id='c')
        self.assertEqual(result['text'], 'immediate answer')
        self.assertEqual([e['type'] for e in self.events.read()], ['question.requested', 'question.answered'])

    def test_publication_failure_keeps_tool_error_and_cancels_question(self):
        def emit(kind, **data):
            self.events.append(kind, **data)
            if kind == 'question.requested':
                raise RuntimeError('subscriber failed')
        gate = QuestionGate(emit)
        router = ToolRouter(self.root, ask_user=gate.request)
        result = router.call('ask_user', {'question': 'q'}, self.context)
        self.assertIn('[tool error] RuntimeError: subscriber failed', result)
        self.assertEqual(gate.snapshot(), {'pending': []})
        self.assertEqual(self.events.read()[-1]['reason'], 'tool_failed')

    def test_cancel_wakes_wait_and_persists_cancellation_and_rejects_answer(self):
        thread, result, item = self.start_call({'question': 'q'})
        self.context.cancellation.cancel()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(result[0], RunCancelled)
        self.assertEqual(self.gate.snapshot(), {'pending': []})
        self.assertEqual(self.events.read()[-1]['type'], 'question.cancelled')
        with self.assertRaises(QuestionConflict):
            self.gate.answer(item['questionId'], text='too late')

    def test_already_cancelled_does_not_publish(self):
        self.context.cancellation.cancel()
        with self.assertRaises(RunCancelled):
            self.router.call('ask_user', {'question': 'q'}, self.context)
        self.assertEqual(self.events.read(), [])

    def test_callback_removal_never_holds_question_condition(self):
        original = self.context.cancellation.add_callback
        checked = []
        def add_callback(callback):
            remove = original(callback)
            def guarded_remove():
                # Mimic callback removal that waits for an in-flight wake callback.
                t = threading.Thread(target=callback)
                t.start()
                t.join(1)
                checked.append(not t.is_alive())
                remove()
            return guarded_remove
        self.context.cancellation.add_callback = add_callback
        thread, result, item = self.start_call({'question': 'q'})
        self.gate.answer(item['questionId'], text='answer')
        thread.join(3)
        self.assertEqual(checked, [True])

    def test_cancel_answer_race_never_hangs_and_has_one_terminal_event(self):
        for i in range(20):
            self.context = ExecutionContext(CancellationToken())
            thread, result, item = self.start_call({'question': f'q{i}'})
            barrier = threading.Barrier(3)
            def answer():
                barrier.wait()
                try:
                    self.gate.answer(item['questionId'], text='answer')
                except QuestionConflict:
                    pass
            def cancel():
                barrier.wait()
                self.context.cancellation.cancel()
            workers = [threading.Thread(target=answer), threading.Thread(target=cancel)]
            for t in workers: t.start()
            barrier.wait()
            for t in workers: t.join(3)
            thread.join(3)
            self.assertFalse(thread.is_alive())
            terminal = [e for e in self.events.read() if e.get('questionId') == item['questionId']
                        and e['type'] != 'question.requested']
            self.assertEqual(len(terminal), 1)
            self.assertEqual(self.gate.snapshot(), {'pending': []})

    def test_restart_cancels_stale_and_restores_identical_answer_retries(self):
        self.events.append('question.requested', questionId='stale', callId='c', runId='r',
                           question='old question', options=[])
        self.events.append('question.requested', questionId='answered', callId='c2', runId='r',
                           question='resolved', options=options())
        self.events.append('question.answered', questionId='answered', callId='c2', runId='r',
                           answer={'option_index': 0, 'text': options()[0]['title'] + '\n' + options()[0]['description']})
        restored = QuestionGate(self.events.append, self.events.read())
        self.assertEqual(restored.snapshot(), {'pending': []})
        self.assertEqual(self.events.read()[-1]['reason'], 'process_restarted')
        with self.assertRaises(QuestionConflict):
            restored.answer('stale', text='late')
        self.assertTrue(restored.answer('answered', option_index=0)['accepted'])
        with self.assertRaises(QuestionConflict):
            restored.answer('answered', text='different')
        count = len(self.events.read())
        QuestionGate(self.events.append, self.events.read())
        self.assertEqual(len(self.events.read()), count)


class QuestionApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = replace(load(), storage_dir=self.root / 'storage', workspace=self.root,
                              mcp={}, context={'enabled': False}, approval_mode='audit', max_rounds=3)
        discovery = patch("agent.web.app.refresh_catalog")
        discovery.start()
        self.addCleanup(discovery.stop)
        self.registry = SessionRegistry(self.config)
        self.main = self.registry.create()
        self.addCleanup(self.close)

    def close(self):
        for rt in self.registry.items.values(): rt.stop()
        self.registry.wait()
        for rt in self.registry.items.values(): rt.queue.put(None)
        for rt in self.registry.items.values(): rt.worker.join(3)

    def fake_stream(self, client, model, messages, schemas, **kwargs):
        if messages[-1]['role'] == 'user':
            self.assertIn('ask_user', [s['function']['name'] for s in schemas])
            yield ModelChunk(tool_deltas=(ToolCallDelta(0, 'ask', 'ask_user',
                json.dumps({'question': '请选择任意方向', 'options': options()})),), finish_reason='tool_calls')
        else:
            tool_answer = json.loads(messages[-1]['content'])
            self.assertEqual(messages[-1]['role'], 'tool')
            self.assertEqual(tool_answer['title'], options()[1]['title'])
            self.assertEqual(tool_answer['description'], options()[1]['description'])
            yield ModelChunk(tool_deltas=(ToolCallDelta(0, 'done', 'submit',
                json.dumps({'content': 'The chosen direction is implemented.'})),), finish_reason='tool_calls')

    def test_api_runtime_roundtrip_validation_replay_retry_and_child_answer(self):
        child = self.registry.create(parent_session_id=self.main.session.id)
        with patch.object(web, 'registry', self.registry), patch.object(web, 'session_store', self.registry.store), \
             patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())), \
             patch('agent.workflows.turn.nodes.stream', side_effect=self.fake_stream), TestClient(web.app) as client:
            for rt in (self.main, child):
                with self.subTest(child=bool(rt.parent_session_id)):
                    path = f'/api/sessions/{rt.session.id}'
                    if rt.parent_session_id:
                        self.assertEqual(client.post(path + '/messages', json={'content': 'no'}).status_code, 400)
                        rt.start('ask then implement')
                    else:
                        self.assertEqual(client.post(path + '/messages', json={'content': 'ask then implement'}).status_code, 200)
                    wait_until(lambda: rt.questions.snapshot()['pending'])
                    pending = client.get(path + '/questions').json()['pending']
                    self.assertEqual(len(pending), 1)
                    item = pending[0]
                    self.assertEqual(item['options'], options())
                    endpoint = path + f'/questions/{item["questionId"]}/answer'
                    for body, status in (({}, 400), ({'text': ' '}, 400), ({'option_index': 3}, 400),
                                         ({'option_index': -1}, 400), ({'option_index': True}, 422),
                                         ({'option_index': 1.0}, 422), ({'option_index': '1'}, 422),
                                         ({'text': 1}, 422), ({'text': 'x' * 4001}, 422),
                                         ({'unknown': 'x'}, 422)):
                        self.assertEqual(client.post(endpoint, json=body).status_code, status, body)
                    response = client.post(endpoint, json={'option_index': 1})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()['answer'], {'option_index': 1,
                        'text': options()[1]['title'] + '\n' + options()[1]['description']})
                    self.assertEqual(client.post(endpoint, json={'option_index': 1}).json(), response.json())
                    self.assertEqual(client.post(endpoint, json={'option_index': 0}).status_code, 409)
                    self.registry.wait()
                    self.assertEqual(client.get(path + '/questions').json(), {'pending': []})
                    self.assertEqual(client.post(path + '/questions/missing/answer', json={'text': 'a'}).status_code, 404)
                    self.assertEqual(rt.approvals.snapshot()['pending'], [])
                    records = rt.session.events.read()
                    self.assertEqual([e['type'] for e in records if e['type'].startswith('question.')],
                                     ['question.requested', 'question.answered'])
                    self.assertFalse(any(e['type'].startswith('approval.') for e in records))
                    completed = next(e for e in records if e['type'] == 'tool.completed' and e['tool'] == 'ask_user')
                    self.assertEqual(json.loads(completed['result'])['description'], options()[1]['description'])
                    replay = restore_model_messages(records, {'role': 'system', 'content': 'system'})
                    restored_tool = next(m for m in replay if m.get('tool_call_id') == 'ask')
                    self.assertEqual(json.loads(restored_tool['content'])['option_index'], 1)
                    self.assertEqual(records[-1]['type'], 'turn.completed')

    def test_full_bounded_custom_answer_reaches_model_without_spill_truncation(self):
        answer = '完整答案' * 1000  # 4000 characters, above the normal line preview limit.
        seen = []
        def stream(client, model, messages, schemas, **kwargs):
            if messages[-1]['role'] == 'user':
                yield ModelChunk(tool_deltas=(ToolCallDelta(0, 'long-ask', 'ask_user',
                    json.dumps({'question': '请提供完整答案', 'options': []})),), finish_reason='tool_calls')
            else:
                value = json.loads(messages[-1]['content'])
                seen.append(value)
                self.assertEqual(value['text'], answer)
                self.assertIsNone(value['option_index'])
                yield ModelChunk(tool_deltas=(ToolCallDelta(0, 'done', 'submit',
                    json.dumps({'content': 'Done.'})),), finish_reason='tool_calls')
        with patch.object(web, 'registry', self.registry), patch.object(web, 'session_store', self.registry.store), \
             patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())), \
             patch('agent.workflows.turn.nodes.stream', side_effect=stream), TestClient(web.app) as client:
            self.main.enqueue('ask')
            wait_until(lambda: self.main.questions.snapshot()['pending'])
            item = self.main.questions.snapshot()['pending'][0]
            path = f'/api/sessions/{self.main.session.id}/questions/{item["questionId"]}/answer'
            self.assertEqual(client.post(path, json={'text': answer, 'option_index': None}).status_code, 200)
            self.registry.wait()
            self.assertEqual(len(seen), 1)
            records = self.main.session.events.read()
            completed = next(e for e in records if e['type'] == 'tool.completed' and e['tool'] == 'ask_user')
            self.assertEqual(json.loads(completed['result'])['text'], answer)
            self.assertEqual(records[-1]['type'], 'turn.completed')

    def test_api_stop_cancels_worker_without_holding_session_lock(self):
        with patch.object(web, 'registry', self.registry), patch.object(web, 'session_store', self.registry.store), \
             patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())), \
             patch('agent.workflows.turn.nodes.stream', side_effect=self.fake_stream), TestClient(web.app) as client:
            self.main.enqueue('ask')
            wait_until(lambda: self.main.questions.snapshot()['pending'])
            item = self.main.questions.snapshot()['pending'][0]
            path = f'/api/sessions/{self.main.session.id}'
            self.assertEqual(client.post(path + '/control/stop').json(), {'stopped': True})
            self.registry.wait()
            self.assertEqual(client.get(path + '/questions').json(), {'pending': []})
            self.assertEqual(client.post(path + f'/questions/{item["questionId"]}/answer', json={'text': 'late'}).status_code, 409)
            records = self.main.session.events.read()
            self.assertEqual(records[-1]['type'], 'turn.cancelled')
            self.assertTrue(any(e['type'] == 'question.cancelled' for e in records))
            self.assertTrue(any(e['type'] == 'tool.completed' and '[tool cancelled]' in e['result'] for e in records))

    def test_api_restart_recovery_and_persisted_custom_answer_retry(self):
        session_id = self.main.session.id
        self.main.session.events.append('question.requested', questionId='stale', callId='old', runId='old-run',
                                        question='q', options=[])
        self.main.session.events.append('question.requested', questionId='done', callId='done', runId='old-run',
                                        question='q2', options=[])
        self.main.session.events.append('question.answered', questionId='done', callId='done', runId='old-run',
                                        answer={'option_index': None, 'text': 'persisted custom'})
        recreated = SessionRegistry(self.config)
        try:
            with patch.object(web, 'registry', recreated), patch.object(web, 'session_store', recreated.store), TestClient(web.app) as client:
                path = f'/api/sessions/{session_id}/questions'
                self.assertEqual(client.get(path).json(), {'pending': []})
                self.assertEqual(client.post(path + '/stale/answer', json={'text': 'late'}).status_code, 409)
                self.assertEqual(client.post(path + '/done/answer', json={'text': 'persisted custom'}).status_code, 200)
                self.assertEqual(client.post(path + '/done/answer', json={'text': 'conflicting'}).status_code, 409)
                records = recreated.get(session_id).session.events.read()
                self.assertEqual(records[-1]['type'], 'question.cancelled')
                self.assertEqual(records[-1]['questionId'], 'stale')
        finally:
            for rt in recreated.items.values(): rt.queue.put(None)
            for rt in recreated.items.values(): rt.worker.join(3)

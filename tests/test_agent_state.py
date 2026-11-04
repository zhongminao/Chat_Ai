import json
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from unittest.mock import Mock, patch

from agent.core.session_registry import SessionRegistry
from agent.core.agent_factory import build_state
from agent.model.protocol import ModelChunk, ToolCallDelta
from agent.agentsessionstate.commands import SwitchModel
from agent.agentsessionstate.message_updates import time_notice, is_time_notice
from agent.agentsessionstate.config import load
from agent.agentsessionstate.message_replay import restore_display_messages, restore_model_messages


class AgentStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        config = replace(load(), approval_mode="full_access", workspace=root, storage_dir=root, mcp={}, max_rounds=2)
        self.registry = SessionRegistry(config)
        self.clients = patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object()))
        self.runtime_factory = self.clients.start()
        self.session = self.registry.create()
        self.agent = self.session.agent

    def tearDown(self):
        for runtime in self.registry.items.values():
            runtime.stop()
        self.registry.wait()
        for runtime in self.registry.items.values():
            runtime.queue.put(None)
            runtime.worker.join(5)
        self.clients.stop()
        self.temp.cleanup()

    def serializable(self):
        return json.loads(json.dumps(self.agent.state, ensure_ascii=False, allow_nan=False))

    def test_time_is_sampled_once_per_turn_and_preserved_across_model_loops(self):
        moments = [datetime(2026, 11, 4, 23, 59, 59, tzinfo=ZoneInfo('Asia/Shanghai')),
                   datetime(2026, 11, 5, 0, 0, 1, tzinfo=ZoneInfo('Asia/Shanghai'))]
        snapshots = []
        self.agent.context_config = {'enabled': False}

        def stream(client, model, messages, schemas, **kwargs):
            snapshots.append(json.loads(json.dumps(messages)))
            if messages[-1]['role'] == 'user':
                yield ModelChunk(tool_deltas=(ToolCallDelta(id='read', name='read_file',
                                 arguments=json.dumps({'path': 'not-present.txt'})),))
            else:
                yield ModelChunk(content='done')

        with patch('agent.core.agent_runtime.datetime') as clock, \
             patch('agent.core.agent_runtime.stream', side_effect=stream):
            clock.now.side_effect = moments
            for text in ['first turn', 'next turn']:
                self.session.enqueue(text)
                self.registry.wait()
            self.assertEqual(clock.now.call_count, 2)
            self.assertTrue(all(str(call.args[0]) == 'Asia/Shanghai' for call in clock.now.call_args_list))
        self.assertEqual(len(snapshots), 4)
        expected_times = [time_notice(moment.isoformat(timespec='seconds')) for moment in moments]
        for i, snapshot in enumerate(snapshots):
            self.assertEqual([m for m in snapshot if is_time_notice(m)], expected_times[:1 + i // 2])
        events = self.session.session.events.read()
        turns = [event for event in events if event['type'] == 'turn.started']
        self.assertEqual([event['currentTime'] for event in turns],
                         [moment.isoformat(timespec='seconds') for moment in moments])
        self.assertEqual(restore_model_messages(events, self.agent.state['messages'][0]), self.agent.state['messages'])
        self.assertFalse(any(is_time_notice(message) for message in restore_display_messages(events)))
        self.assertFalse(any('当前时间' in row.get('text', '') for row in events if row['type'] == 'message.delta'))

    def test_model_switch_and_messages_use_the_same_state(self):
        state = self.agent.state
        self.assertIsNone(self.serializable()['execution'])
        self.assertEqual(state['messages'][0]['role'], 'system')
        self.runtime_factory.assert_not_called()
        target = {**state['model'], 'name': 'another-model'}
        with patch.object(self.agent.catalog, 'resolve', return_value=Mock(as_dict=lambda: target)):
            self.session.dispatch(SwitchModel(provider=target['provider'], model=target['name']))
        self.assertIs(self.agent.state, state)
        self.runtime_factory.assert_not_called()

        def stream(client, model, messages, schemas, **kwargs):
            self.assertEqual(model, target['name'])
            self.assertIs(messages, state['messages'])
            self.assertEqual(self.serializable()['execution']['status'], 'running')
            yield ModelChunk(content='short reply')

        with patch('agent.core.agent_runtime.stream', side_effect=stream):
            self.session.enqueue('hello')
            self.registry.wait()
        execution = self.serializable()['execution']
        self.assertEqual((execution['status'], execution['phase'], execution['answer']),
                         ('completed', 'done', 'short reply'))
        self.assertEqual(state['messages'][-1]['content'], 'short reply')
        self.assertIsNone(execution['report'])
        self.runtime_factory.assert_called_once()

    def test_runtime_requests_binding_from_current_state_model(self):
        first = (object(), object())
        second = (object(), object())
        self.runtime_factory.side_effect = [first, first, second]
        observed = []

        def stream(client, model, messages, schemas, **kwargs):
            observed.append((client, kwargs['provider']))
            yield ModelChunk(content='ok')

        with patch('agent.core.agent_runtime.stream', side_effect=stream):
            for _ in range(2):
                self.session.enqueue('hello')
                self.registry.wait()
            target = {**self.agent.state['model'], 'name': 'another-model'}
            with patch.object(self.agent.catalog, 'resolve', return_value=Mock(as_dict=lambda: target)):
                self.session.dispatch(SwitchModel(provider=target['provider'], model=target['name']))
            self.assertEqual(self.runtime_factory.call_count, 2)
            self.session.enqueue('hello again')
            self.registry.wait()
        self.assertEqual(observed, [first, first, second])
        self.assertEqual([call.args[0].name for call in self.runtime_factory.call_args_list],
                         [self.registry.config.model['name'], self.registry.config.model['name'], target['name']])

    def test_submit_and_next_turn_do_not_share_execution_data(self):
        def submit_stream(*args, **kwargs):
            yield ModelChunk(tool_deltas=(ToolCallDelta(id='report', name='submit',
                             arguments=json.dumps({'content': '# Final report'})),))

        with patch('agent.core.agent_runtime.stream', side_effect=submit_stream):
            self.session.enqueue('report')
            self.registry.wait()
        report = self.serializable()['execution']
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(Path(report['report_path']).read_text().strip(), report['report'])
        self.assertEqual(report['answer'], report['report'])

        with patch('agent.core.agent_runtime.stream', return_value=iter([ModelChunk(content='hello')])):
            self.session.enqueue('chat')
            self.registry.wait()
        current = self.serializable()['execution']
        self.assertNotEqual(current['id'], report['id'])
        self.assertIsNone(current['report'])
        self.assertIsNone(current['report_path'])
        self.assertEqual(report['report'], '# Final report')

    def test_stop_during_tools_keeps_state_and_history_consistent(self):
        entered = threading.Event()

        def stream(*args, **kwargs):
            yield ModelChunk(content='Waiting for a tool.', tool_deltas=(
                ToolCallDelta(id='wait', name='watch', arguments='{}'),))

        def wait(context, **kwargs):
            self.assertEqual(self.serializable()['execution']['phase'], 'tools')
            stopped = threading.Event()
            remove = context.cancellation.add_callback(stopped.set)
            try:
                entered.set()
                self.assertTrue(stopped.wait(5))
            finally:
                remove()
            context.cancellation.raise_if_cancelled()

        with patch('agent.core.agent_runtime.stream', side_effect=stream), patch.object(self.agent.tools, 'watch', side_effect=wait):
            self.session.enqueue('wait')
            self.assertTrue(entered.wait(5))
            self.session.stop()
            self.registry.wait()
        execution = self.serializable()['execution']
        self.assertEqual((execution['status'], execution['phase']), ('cancelled', 'done'))
        history = restore_display_messages(self.session.session.events.read())
        visible = [message for message in self.agent.state['messages'][1:] if not is_time_notice(message)]
        self.assertEqual(visible,
                         [{key: value for key, value in message.items() if key != 'name'} for message in history])
        self.assertEqual(restore_model_messages(self.session.session.events.read(), self.agent.state['messages'][0]),
                         self.agent.state['messages'])

    def test_error_and_round_limit_update_execution_status(self):
        for failure in (RuntimeError('model unavailable'), None):
            def stream(*args, **kwargs):
                if failure:
                    raise failure
                yield ModelChunk(tool_deltas=(ToolCallDelta(id='read', name='read_file',
                    arguments=json.dumps({'path': 'missing.txt'})),))

            with self.subTest(failure=failure), patch('agent.core.agent_runtime.stream', side_effect=stream):
                self.session.enqueue('work')
                self.registry.wait()
                execution = self.serializable()['execution']
                self.assertEqual((execution['status'], execution['phase']), ('failed', 'done'))
                self.assertIn('model unavailable' if failure else 'maximum model rounds', execution['error'])

    def test_network_failure_keeps_inputs_and_replays_the_same_messages(self):
        for partial in ['', 'unfinished reply']:
            with self.subTest(partial=partial):
                prompt = ' A\n原始输入  '
                before = self.serializable()['messages']

                def fail(*args, **kwargs):
                    if partial:
                        yield ModelChunk(content=partial)
                    raise ConnectionError('network unavailable')

                with patch('agent.core.agent_runtime.stream', side_effect=fail):
                    self.session.enqueue(prompt)
                    self.registry.wait()
                records = self.session.session.events.read()
                turn = next(event for event in reversed(records) if event['type'] == 'turn.started')
                expected = [*before, time_notice(turn['currentTime']), {'role': 'user', 'content': prompt}]
                self.assertEqual(self.agent.state['messages'], expected)
                self.assertEqual(self.agent.state['execution']['status'], 'failed')
                self.assertEqual(restore_model_messages(records, expected[0]), expected)
                self.assertEqual(build_state(self.registry.config, self.session.meta, records)['messages'], expected)

                def reply(client, model, messages, schemas, **kwargs):
                    self.assertEqual(messages[:-2], expected)
                    self.assertTrue(is_time_notice(messages[-2]))
                    self.assertEqual(messages[-1], {'role': 'user', 'content': 'B'})
                    yield ModelChunk(content='received A and B')

                with patch('agent.core.agent_runtime.stream', side_effect=reply):
                    self.session.enqueue('B')
                    self.registry.wait()
                self.assertEqual(restore_model_messages(self.session.session.events.read(), expected[0]),
                                 self.agent.state['messages'])

    def test_reopened_session_sends_failed_input_before_the_next_input(self):
        with patch('agent.core.agent_runtime.stream', side_effect=ConnectionError('network unavailable')):
            self.session.enqueue('A')
            self.registry.wait()
        expected = self.serializable()['messages']
        reopened = SessionRegistry(self.registry.config)
        runtime = reopened.get(self.session.session.id)
        try:
            self.assertEqual(runtime.state['messages'], expected)

            def reply(client, model, messages, schemas, **kwargs):
                self.assertEqual(messages[:-2], expected)
                self.assertTrue(is_time_notice(messages[-2]))
                self.assertEqual(messages[-1], {'role': 'user', 'content': 'B'})
                yield ModelChunk(content='received A and B')

            with patch('agent.core.agent_runtime.stream', side_effect=reply):
                runtime.enqueue('B')
                reopened.wait()
            self.assertEqual(restore_model_messages(runtime.session.events.read(), expected[0]),
                             runtime.state['messages'])
        finally:
            runtime.stop()
            reopened.wait()
            runtime.queue.put(None)
            runtime.worker.join(5)
            reopened.store.database.close()


    def test_large_bash_output_is_saved_and_the_turn_continues(self):
        import shlex
        import sys

        self.agent.context_config = {"enabled": False}
        command = shlex.quote(sys.executable) + " -c " + shlex.quote("print('x' * 20000)")

        def stream(client, model, messages, schemas, **kwargs):
            if messages[-1]["role"] == "user":
                yield ModelChunk(tool_deltas=(ToolCallDelta(id="large-output", name="run_bash",
                    arguments=json.dumps({"command": command})),))
            else:
                self.assertEqual(messages[-1]["role"], "tool")
                self.assertIn("[spill]", messages[-1]["content"])
                self.assertLess(len(messages[-1]["content"]), 12000)
                path, = (self.agent.workspace / ".spill" / self.session.session.id).glob("*.log")
                self.assertEqual(path.read_text(), "x" * 20000 + "\n")
                yield ModelChunk(content="large output received")

        with patch("agent.core.agent_runtime.stream", side_effect=stream):
            self.session.enqueue("produce large output")
            self.registry.wait()
        records = self.session.session.events.read()
        self.assertTrue(any(event["type"] == "tool.completed" for event in records))
        self.assertEqual(records[-1]["type"], "turn.completed")
        self.assertEqual(self.agent.state["execution"]["status"], "completed")


if __name__ == '__main__':
    unittest.main()

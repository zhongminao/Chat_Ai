"""End-to-end task steering with real sessions, mail and graph boundaries."""
import copy
import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from agent.agentsessionstate.config import load
from agent.agentsessionstate.message_replay import restore_model_messages
from agent.core.session_registry import SessionRegistry
from agent.core.steering import InputDelivery
from agent.model.protocol import ModelChunk, ToolCallDelta
from agent.web.history import display_event, history_page


def calls(*items):
    return ModelChunk(tool_deltas=tuple(ToolCallDelta(i, name, name, json.dumps(args))
                                        for i, (name, args) in enumerate(items)), finish_reason='tool_calls')


class AgentCorrectionTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.registry = SessionRegistry(replace(load(), storage_dir=root / 'storage', workspace=root,
                                                mcp={}, context={'enabled': False}, approval_mode='full_access'))
        self.main = self.registry.create()
        self.child = self.registry.create(parent_session_id=self.main.session.id)
        self.parent_id, self.child_id = self.main.session.id, self.child.session.id
        self.started, self.release = threading.Event(), threading.Event()
        self.requests = []
        self.enterContext(patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())))
        self.addCleanup(self.close)

    def close(self):
        self.release.set()
        for runtime in self.registry.items.values():
            runtime.stop()
            runtime.queue.put(None)
            runtime.worker.join(5)
        self.registry.store.database.close()

    def start(self, initial):
        def stream(_client, _model, messages, *_args, context, **_kwargs):
            self.requests.append(copy.deepcopy(messages))
            if len(self.requests) == 1:
                yield from initial(context)
            else:
                yield calls(('submit', {'content': 'done'}))
        self.enterContext(patch('agent.workflows.turn.nodes.stream', side_effect=stream))
        self.child.start('original child task')
        self.assertTrue(self.started.wait(3), 'child did not reach its running step')

    def inspect(self):
        return self.registry.inspect_agent(self.parent_id, self.child_id)

    def correct(self, step_id=None):
        result = self.main.agent.tools.call('notify_agent', {
            'to': self.child_id, 'content': 'private revision', 'interrupt': True,
            **({'step_id': step_id} if step_id else {}),
        })
        return json.loads(result)

    def finish(self, message_id):
        self.registry.wait()
        records = self.child.session.events.read()
        self.assertEqual(len(self.requests), 2, records)
        self.assertEqual(self.requests[1][-1]['role'], 'user')
        self.assertIn('private revision', self.requests[1][-1]['content'])
        self.assertEqual([r['type'] for r in records if r['type'].startswith('turn.')],
                         ['turn.started', 'turn.completed'])
        self.assertEqual(self.inspect()['latest_correction'], 'private revision')
        self.assertEqual(restore_model_messages(records, self.requests[0][0]), self.child.state['messages'])
        self.assertNotIn('private revision', str(history_page(self.child.session.events)))
        self.assertIsNotNone(self.registry.mailbox_list(self.child_id)[0]['read_at'])
        self.assertEqual(self.registry.mailbox_list(self.child_id)[0]['id'], message_id)
        return records

    def test_interrupt_running_tool_and_skip_remaining_calls(self):
        def first(_context):
            yield calls(('read_file', {'path': 'one'}), ('bash', {'command': 'echo two'}))
        def tool(_root, _name, _args, context, **_kwargs):
            self.started.set()
            while not self.release.wait(.01):
                context.cancellation.raise_if_cancelled()
            return 'natural result'
        execute = self.enterContext(patch('agent.tools.router.execute', side_effect=tool))
        self.start(first)
        snapshot = json.loads(self.main.agent.tools.call('inspect_agent', {'session_id': self.child_id}))
        self.assertEqual(snapshot['task_input'], 'original child task')
        self.assertIsNone(snapshot['latest_correction'])
        self.assertEqual(snapshot['current_tool']['arguments'], {'path': 'one'})
        self.assertEqual(snapshot['pending_tools'], [
            {'call_id': 'bash', 'tool': 'bash', 'arguments': {'command': 'echo two'}},
        ])
        result = self.correct(snapshot['step_id'])
        self.assertEqual(result['action'], 'interrupt_requested')
        records = self.finish(result['id'])
        self.assertEqual(execute.call_count, 1)
        self.assertEqual([e.get('status') for e in records if e['type'] == 'tool.completed'],
                         ['interrupted', 'skipped', None])
        self.assertEqual([r['tool'] for r in records if r['type'] == 'tool.requested'], ['read_file', 'submit'])
        self.assertEqual([m['role'] for m in self.requests[1][-4:]], ['assistant', 'tool', 'tool', 'user'])

    def test_stale_step_keeps_natural_result_then_skips_unstarted_tools(self):
        def first(_context):
            yield calls(('read_file', {'path': 'one'}), ('bash', {'command': 'echo two'}))
        def tool(_root, _name, _args, context, **_kwargs):
            self.started.set()
            self.assertTrue(self.release.wait(3))
            context.cancellation.raise_if_cancelled()
            return 'natural result'
        self.enterContext(patch('agent.tools.router.execute', side_effect=tool))
        self.start(first)
        result = self.correct('stale-step')
        self.assertEqual(result['action'], 'at_boundary')
        self.assertIsNone(self.inspect()['latest_correction'])
        self.release.set()
        records = self.finish(result['id'])
        self.assertEqual([e['result'] for e in records if e['type'] == 'tool.completed'][:2],
                         ['natural result', '[tool skipped] Parent sent a correction.'])

    def test_model_interrupt_does_not_execute_or_expose_partial_call(self):
        def first(context):
            yield ModelChunk(content='unfinished text', tool_deltas=(ToolCallDelta(0, 'partial', 'bash', '{"com'),))
            self.started.set()
            while not self.release.wait(.01):
                context.cancellation.raise_if_cancelled()
        self.start(first)
        snapshot = self.inspect()
        self.assertEqual(snapshot['phase'], 'model')
        self.assertEqual(snapshot['pending_tools'], [])
        result = self.correct(snapshot['step_id'])
        records = self.finish(result['id'])
        self.assertEqual([e['round'] for e in records if e['type'] == 'model.started'], [0, 1])
        self.assertEqual([e['answer'] for e in records if e['type'] == 'model.interrupted'], ['unfinished text'])
        self.assertEqual([e['tool'] for e in records if e['type'] == 'tool.requested'], ['submit'])

    def test_child_watch_returns_normally_and_parent_gets_live_receipt(self):
        def first(_context):
            yield calls(('watch', {'cursor': 0, 'timeout': 10}))
        child_monitor = self.registry.monitor(self.child_id)
        wait = child_monitor.condition.wait
        def signal_wait(*args):
            self.started.set()
            return wait(*args)
        self.enterContext(patch.object(child_monitor.condition, 'wait', side_effect=signal_wait))
        self.start(first)
        monitor = self.registry.monitor(self.parent_id)
        waiting = threading.Event()
        receipts = []
        cursor = monitor.watch()['cursor']
        waiter = threading.Thread(target=lambda: receipts.append(
            monitor.watch(cursor, 5, detail_level='detailed', wake_if=lambda: waiting.set())), daemon=True)
        waiter.start()
        self.assertTrue(waiting.wait(3))
        result = self.correct(self.inspect()['step_id'])
        self.assertEqual(result['action'], 'wake_watch')
        records = self.finish(result['id'])
        waiter.join(3)
        self.assertEqual(receipts[0]['read_receipts'], [
            {'message_id': result['id'], 'recipient_id': self.child_id},
        ])
        watch_result = next(e for e in records if e['type'] == 'tool.completed' and e['tool'] == 'watch')
        self.assertNotIn('status', watch_result)
        self.assertTrue(json.loads(watch_result['result'])['interrupted_by_guidance'])

    def test_waiting_approval_is_cancelled_not_approved(self):
        self.main.approvals.set_mode('audit')
        def first(_context):
            yield calls(('bash', {'command': 'echo must-not-run'}))
        append = self.main.approvals._emit
        def emit(kind, **fields):
            result = append(kind, **fields)
            if kind == 'approval.requested':
                self.started.set()
            return result
        self.enterContext(patch.object(self.main.approvals, '_emit', side_effect=emit))
        execute = self.enterContext(patch('agent.tools.router.execute'))
        self.start(first)
        result = self.correct()
        records = self.finish(result['id'])
        execute.assert_not_called()
        self.assertEqual(self.main.approvals.snapshot()['pending'], [])
        self.assertEqual([e['decision'] for e in self.main.session.events.read() if e['type'] == 'approval.resolved'],
                         ['cancelled'])
        self.assertEqual(next(e['status'] for e in records if e['type'] == 'tool.completed'), 'interrupted')

    def test_dispatched_remote_tool_finishes_before_correction_is_delivered(self):
        tool_name = 'remote_work'
        router = self.child.agent.tools
        router.mcp.tools[tool_name] = ('fake', 'work')
        router.schemas.append({'type': 'function', 'function': {'name': tool_name}})
        def first(_context):
            yield calls((tool_name, {}), ('bash', {'command': 'echo skipped'}))
        def remote(_name, _arguments, context):
            self.started.set()
            self.assertTrue(self.release.wait(3))
            context.cancellation.raise_if_cancelled()
            return 'remote result'
        self.enterContext(patch.object(router.mcp, 'call', side_effect=remote))
        self.enterContext(patch('agent.tools.router.convert_result', side_effect=lambda text, *_a, **_kw: text))
        self.start(first)
        result = self.correct(self.inspect()['step_id'])
        self.assertEqual(len(self.requests), 1)
        self.assertIsNone(self.inspect()['latest_correction'])
        self.assertEqual(self.registry.mailbox_unread_count(self.child_id), 1)
        self.release.set()
        records = self.finish(result['id'])
        self.assertEqual(next(e['result'] for e in records if e['type'] == 'tool.completed'), 'remote result')

    def test_turn_stop_takes_priority_over_local_interruption(self):
        def first(_context):
            yield calls(('read_file', {'path': 'one'}), ('bash', {'command': 'echo two'}))
        def tool(_root, _name, _args, context, **_kwargs):
            self.started.set()
            self.assertTrue(self.release.wait(3))
            context.cancellation.raise_if_cancelled()
        self.enterContext(patch('agent.tools.router.execute', side_effect=tool))
        self.start(first)
        result = self.correct(self.inspect()['step_id'])
        self.assertTrue(self.child.stop())
        self.release.set()
        self.registry.wait()
        records = self.child.session.events.read()
        self.assertEqual([r['type'] for r in records if r['type'].startswith('turn.')],
                         ['turn.started', 'turn.cancelled'])
        results = [r['result'] for r in records if r['type'] == 'tool.completed']
        self.assertEqual(len(results), 2)
        self.assertTrue(all(text.startswith('[tool cancelled]') for text in results))
        self.assertIsNone(self.registry.mailbox_list(self.child_id)[0]['read_at'])
        self.assertEqual(self.registry.mailbox_list(self.child_id)[0]['id'], result['id'])

    def test_authorization_and_display_redaction(self):
        with self.assertRaises(ValueError):
            self.registry.notify_agent(self.parent_id, self.child_id, 'inactive', interrupt=True)
        with self.assertRaises(PermissionError):
            self.registry.notify_agent(self.child_id, self.parent_id, 'not parent', interrupt=True)
        with self.assertRaises(PermissionError):
            self.registry.notify_agent(self.parent_id, self.child_id, 'no cc', cc=['other'], interrupt=True)
        with self.assertRaises(PermissionError):
            self.registry.inspect_agent(self.child_id, self.parent_id)
        for event in [
            {'type': 'tool_call.delta', 'delta': {'arguments': 'secret'}},
            {'type': 'tool.requested', 'tool': 'notify_agent', 'arguments': {'content': 'secret'}},
            {'type': 'tool.completed', 'tool': 'inspect_agent', 'result': 'secret'},
            {'type': 'tool.completed', 'tool': 'read_agent_message', 'result': 'secret'},
        ]:
            self.assertNotIn('secret', str(display_event(event)))

    def test_durable_delivery_ack_repairs_without_reinjecting(self):
        item = {'id': 'letter', 'sender_id': 'parent', 'content': 'revision', 'kind': 'correction'}
        records, acks = [], []
        emit = lambda kind, **kw: records.append({'type': kind, **kw})
        delivery = InputDelivery(threading.RLock(), emit, records, lambda: [item], acks.append)
        self.assertEqual(len(delivery.take('old')), 1)
        self.assertEqual(acks, [])
        resumed = InputDelivery(threading.RLock(), emit, records, lambda: [item], acks.append)
        self.assertEqual(resumed.take('new'), [])
        self.assertEqual(resumed.latest_correction, 'revision')
        resumed.acknowledge_corrections()
        resumed.acknowledge_corrections()
        self.assertEqual(acks, ['letter'])


if __name__ == '__main__':
    unittest.main()

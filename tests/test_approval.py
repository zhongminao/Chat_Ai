import io
import json
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from agent.cli.approval import handle_approval_command, wait_for_execution
from agent.core.cancellation import CancellationToken, ExecutionContext, RunCancelled
from agent.core.session_registry import SessionRegistry
from agent.model.protocol import ModelChunk, ToolCallDelta
from agent.storage.event_log import EventLog
from agent.tools.approval import ApprovalGate
from agent.tools.router import ToolRouter
from agent.web import app as web
from agent.workflow.config import load


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError('condition did not become true')
        time.sleep(.01)


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.events = EventLog(self.root / 'audit.jsonl')
        self.gate = ApprovalGate('audit', self.events.append)
        self.context = ExecutionContext(CancellationToken())
        self.router = ToolRouter(self.root, approval=partial(self.gate.request, session_id='main'))

    def start_call(self, name, arguments):
        result = []
        def run():
            try:
                result.append(self.router.call(name, arguments, self.context, run_id='run', call_id='call'))
            except BaseException as exc:
                result.append(exc)
        thread = threading.Thread(target=run)
        thread.start()
        self.addCleanup(thread.join, 3)
        self.addCleanup(self.context.cancellation.cancel)
        wait_until(lambda: self.gate.snapshot()['pending'])
        return thread, result, self.gate.snapshot()['pending'][0]

    def test_write_requires_each_approval_and_uses_the_reviewed_arguments(self):
        arguments = {'path': 'file.txt', 'content': 'reviewed'}
        thread, result, item = self.start_call('write_file', arguments)
        self.assertFalse((self.root / 'file.txt').exists())
        arguments['content'] = 'changed after request'
        displayed = self.gate.snapshot()
        displayed['pending'][0]['arguments']['content'] = 'mutated UI snapshot'
        with self.assertRaises(ValueError):
            self.gate.set_mode('full_access')
        self.gate.resolve(item['id'], True)
        thread.join(3)
        self.assertEqual((self.root / 'file.txt').read_text(), 'reviewed')
        with self.assertRaises(ValueError):
            self.gate.resolve(item['id'], True)
        thread, result, item = self.start_call('edit_file', {'path': 'file.txt', 'old': 'reviewed', 'new': 'changed'})
        self.gate.resolve(item['id'], False)
        thread.join(3)
        self.assertIn('[tool denied]', result[0])
        self.assertEqual((self.root / 'file.txt').read_text(), 'reviewed')
        decisions = [e['decision'] for e in self.events.read() if e['type'] == 'approval.resolved']
        self.assertEqual(decisions, ['approved', 'rejected'])

    def test_wait_is_cancelled_and_bash_is_never_started(self):
        with patch('agent.tools.executor.subprocess.Popen') as process:
            thread, result, item = self.start_call('run_bash', {'command': 'touch must-not-exist'})
            self.context.cancellation.cancel()
            thread.join(1)
            self.assertFalse(thread.is_alive())
            self.assertIsInstance(result[0], RunCancelled)
            process.assert_not_called()
            self.assertEqual(self.gate.snapshot()['pending'], [])
            self.assertEqual(self.events.read()[-1]['decision'], 'cancelled')
            with self.assertRaises(ValueError):
                self.gate.resolve(item['id'], True)

    def test_cancel_after_approval_still_prevents_execution(self):
        def approve_then_cancel(*args, **kwargs):
            self.context.cancellation.cancel()
            return True
        self.router.approval = approve_then_cancel
        with self.assertRaises(RunCancelled):
            self.router.call('write_file', {'path': 'never', 'content': 'no'}, self.context)
        self.assertFalse((self.root / 'never').exists())

    def test_mcp_reads_also_require_approval_and_unknown_tools_do_not(self):
        tool = 'mcp_example_read_file'
        mcp = SimpleNamespace(tools={tool: ('example', 'read_file')}, schemas=[], call=Mock())
        self.router.mcp = mcp
        self.router.schemas.append({'function': {'name': tool}})
        thread, result, item = self.start_call(tool, {'path': 'remote.txt'})
        mcp.call.assert_not_called()
        with patch('agent.tools.router.convert_result', return_value='remote content'):
            self.gate.resolve(item['id'], True)
            thread.join(3)
        mcp.call.assert_called_once()
        self.assertEqual(result, ['remote content'])
        self.assertIn('当前工具不可用', self.router.call('mcp_missing', {}))
        self.assertEqual(self.gate.snapshot()['pending'], [])

    def test_local_read_and_full_access_do_not_wait(self):
        (self.root / 'file').write_text('readable')
        self.assertEqual(self.router.call('read_file', {'path': 'file'}), 'readable')
        self.assertEqual(self.events.read(), [])
        self.gate.set_mode('full_access')
        self.router.call('write_file', {'path': 'file', 'content': 'written'})
        self.assertEqual((self.root / 'file').read_text(), 'written')
        self.assertEqual(self.events.read()[-1]['type'], 'approval.bypassed')

    def test_parallel_decisions_and_event_sequences_remain_independent(self):
        threads = []
        for index in range(4):
            thread = threading.Thread(target=lambda i=index: self.gate.request('write_file', {'index': i}, self.context,
                session_id=f'child-{i}', run_id=f'run-{i}', call_id=f'call-{i}', is_mcp=False))
            thread.start()
            threads.append(thread)
        wait_until(lambda: len(self.gate.snapshot()['pending']) == 4)
        decisions = [threading.Thread(target=self.gate.resolve, args=(item['id'], True))
                     for item in self.gate.snapshot()['pending']]
        for thread in decisions: thread.start()
        for thread in [*decisions, *threads]: thread.join(3)
        records = self.events.read()
        self.assertEqual([e['seq'] for e in records], list(range(1, 9)))
        self.assertEqual(len({e['id'] for e in records if e['type'] == 'approval.requested'}), 4)


class ApprovalFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = replace(load(), storage_dir=self.root / 'storage', workspace=self.root, mcp={},
                              context={'enabled': False}, approval_mode='audit', max_rounds=3)
        self.registry = SessionRegistry(self.config)
        self.main = self.registry.create()
        self.addCleanup(self.close)

    def close(self):
        for runtime in self.registry.items.values(): runtime.stop()
        self.registry.wait()
        for runtime in self.registry.items.values(): runtime.queue.put(None)
        for runtime in self.registry.items.values(): runtime.worker.join(3)

    def fake_stream(self, client, model, messages, *args, **kwargs):
        if messages[-1]['role'] == 'user':
            yield ModelChunk(tool_deltas=(ToolCallDelta(0, 'write', 'write_file',
                json.dumps({'path': 'output.txt', 'content': 'approved output'})),), finish_reason='tool_calls')
        else:
            yield ModelChunk(content='finished', finish_reason='stop')

    def test_web_child_approval_visible_on_main_refresh_reject_and_stop(self):
        child = self.registry.create(parent_session_id=self.main.session.id)
        self.assertIs(child.approvals, self.main.approvals)
        with patch.object(web, 'registry', self.registry), patch.object(web, 'session_store', self.registry.store), \
             patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())), \
             patch('agent.core.agent_runtime.stream', side_effect=self.fake_stream), TestClient(web.app) as client:
            path = f'/api/sessions/{self.main.session.id}'
            child.start('write something')
            wait_until(lambda: child.approvals.snapshot()['pending'])
            first = client.get(path + '/approvals').json()
            self.assertEqual(client.get(path + '/approvals').json(), first)
            item = first['pending'][0]
            self.assertEqual(item['sessionId'], child.session.id)
            self.assertFalse((self.root / 'output.txt').exists())
            self.assertEqual(client.post(path + '/access', json={'mode': 'full_access'}).status_code, 409)
            self.assertEqual(client.post(path + '/approvals/' + item['id'], json={'approved': False}).status_code, 200)
            self.registry.wait()
            self.assertFalse((self.root / 'output.txt').exists())
            self.assertEqual(client.post(path + '/approvals/' + item['id'], json={'approved': True}).status_code, 409)
            self.main.enqueue('write again')
            wait_until(lambda: self.main.approvals.snapshot()['pending'])
            cancelled = self.main.approvals.snapshot()['pending'][0]
            self.assertEqual(client.post(path + '/control/stop').status_code, 200)
            self.registry.wait()
            self.assertEqual(client.get(path + '/approvals').json()['pending'], [])
            self.assertEqual(client.post(path + '/approvals/' + cancelled['id'], json={'approved': True}).status_code, 409)
            self.assertFalse((self.root / 'output.txt').exists())

    def test_cli_approve_reject_stop_and_mode_commands_use_the_same_gate(self):
        with patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())), \
             patch('agent.core.agent_runtime.stream', side_effect=self.fake_stream), redirect_stdout(io.StringIO()):
            self.main.enqueue('write')
            wait_for_execution(self.registry, self.main, SimpleNamespace(prompt=Mock(return_value='y')))
            self.assertEqual((self.root / 'output.txt').read_text(), 'approved output')
            (self.root / 'output.txt').unlink()
            self.main.enqueue('reject')
            wait_for_execution(self.registry, self.main, SimpleNamespace(prompt=Mock(return_value='n')))
            self.assertFalse((self.root / 'output.txt').exists())
            self.main.enqueue('stop')
            wait_for_execution(self.registry, self.main, SimpleNamespace(prompt=Mock(side_effect=KeyboardInterrupt)))
            self.assertFalse((self.root / 'output.txt').exists())
            self.assertEqual(self.main.state['execution']['status'], 'cancelled')
            self.main.enqueue('stop by command')
            wait_until(lambda: self.main.approvals.snapshot()['pending'])
            self.assertTrue(handle_approval_command('/stop ' + self.main.session.id, self.main.approvals,
                lambda identifier: self.registry.get(identifier).stop()))
            self.registry.wait()
            self.assertFalse((self.root / 'output.txt').exists())
            self.assertTrue(handle_approval_command('/access full_access', self.main.approvals))
            self.main.enqueue('full access')
            wait_for_execution(self.registry, self.main, SimpleNamespace(prompt=Mock(side_effect=AssertionError)))
            self.assertTrue((self.root / 'output.txt').exists())

    def test_mode_restores_but_old_pending_permissions_never_restore(self):
        gate = self.main.approvals
        gate.set_mode('full_access')
        reopened = SessionRegistry(self.config).get(self.main.session.id)
        try:
            self.assertEqual(reopened.approvals.snapshot()['mode'], 'full_access')
            self.assertNotEqual(reopened.approvals.snapshot()['instanceId'], gate.snapshot()['instanceId'])
            self.assertEqual(reopened.approvals.snapshot()['pending'], [])
        finally:
            reopened.queue.put(None); reopened.worker.join(3)
        gate.set_mode('audit')
        context = ExecutionContext(CancellationToken())
        thread = threading.Thread(target=lambda: self.pending_until_cancelled(gate, context))
        thread.start()
        try:
            wait_until(lambda: gate.snapshot()['pending'])
            old_id = gate.snapshot()['pending'][0]['id']
            restarted = SessionRegistry(self.config).get(self.main.session.id)
            try:
                self.assertEqual(restarted.approvals.snapshot()['pending'], [])
                with self.assertRaises(ValueError):
                    restarted.approvals.resolve(old_id, True)
            finally:
                restarted.queue.put(None); restarted.worker.join(3)
        finally:
            context.cancellation.cancel(); thread.join(3)

    def test_cli_entrypoint_reads_approval_on_the_main_thread(self):
        from agent.cli.main import main
        owner = threading.get_ident()
        def approve(prompt):
            self.assertEqual(threading.get_ident(), owner)
            self.assertIn('批准本次', prompt)
            self.assertFalse((self.root / 'output.txt').exists())
            return 'y'
        with patch('sys.argv', ['chat_ai', '--access', 'audit', 'write a file']), \
             patch('agent.cli.main.load', return_value=self.config), \
             patch('agent.cli.main.SessionRegistry', return_value=self.registry), \
             patch('agent.cli.main.PromptSession', return_value=SimpleNamespace(prompt=approve)), \
             patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())), \
             patch('agent.core.agent_runtime.stream', side_effect=self.fake_stream), redirect_stdout(io.StringIO()):
            main()
        self.assertEqual((self.root / 'output.txt').read_text(), 'approved output')

    @staticmethod
    def pending_until_cancelled(gate, context):
        try:
            gate.request('write_file', {}, context, session_id='main', run_id='run', call_id='call', is_mcp=False)
        except RunCancelled:
            pass

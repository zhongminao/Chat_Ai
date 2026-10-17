import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.core.session_registry import SessionRegistry
from agent.web import app as web
from agent.workflow.config import load
from agent.model.protocol import ModelChunk


class SessionApiTests(unittest.TestCase):
    def test_model_switch_changes_state_without_initializing_mcp_or_model_clients(self):
        with tempfile.TemporaryDirectory() as directory:
            config = replace(load(), approval_mode="full_access", storage_dir=Path(directory), mcp={'offline': 'http://127.0.0.1:1/mcp'})
            registry = SessionRegistry(config)
            with patch.object(web, 'registry', registry), patch.object(web, 'session_store', registry.store), TestClient(web.app) as client:
                identifier = client.post('/api/sessions').json()['id']
                path = f'/api/sessions/{identifier}'
                runtime = registry.get(identifier)
                selected = runtime.state['model']
                with patch('agent.core.agent_factory.McpClient', side_effect=AssertionError('MCP must stay disconnected')), \
                     patch('agent.model.catalog.ModelCatalog.get_binding', side_effect=AssertionError('no model client needed')):
                    response = client.post(path + '/model', json={'provider': selected['provider'], 'model': selected['name']})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()['model'], selected)
                    self.assertIsNone(runtime._agent)
                    self.assertEqual(client.get(path + '/conversation').json()['model'], selected)
                    runtime.busy = True
                    try:
                        self.assertEqual(client.post(path + '/model', json={'provider': selected['provider'], 'model': selected['name']}).status_code, 409)
                    finally:
                        runtime.busy = False
                self.assertEqual([event['type'] for event in runtime.session.events.read()], ['model.changed'])
                self.assertEqual(client.delete(path).status_code, 200)
                runtime.worker.join(5)

    def test_first_message_title_is_available_while_reply_is_still_running(self):
        entered, release = threading.Event(), threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            config = replace(load(), approval_mode="full_access", storage_dir=Path(directory), mcp={})
            registry = SessionRegistry(config)

            def stream(*args, **kwargs):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('test did not release model')
                yield ModelChunk(content='你好！')

            with patch.object(web, 'registry', registry), patch.object(web, 'session_store', registry.store), \
                 patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())), \
                 patch('agent.core.agent_runtime.stream', side_effect=stream), TestClient(web.app) as client:
                identifier = client.post('/api/sessions').json()['id']
                runtime = registry.get(identifier)
                try:
                    before = client.get('/api/sessions').json()['sessions'][0]
                    self.assertEqual(before['title'], '新会话')
                    self.assertEqual(client.post(f'/api/sessions/{identifier}/messages', json={'content': '你好'}).status_code, 200)
                    self.assertTrue(entered.wait(5))
                    during = client.get('/api/sessions').json()['sessions'][0]
                    self.assertTrue(during['busy'])
                    self.assertEqual(during['title'], '你好')
                    self.assertEqual(client.patch(f'/api/sessions/{identifier}', json={'title': '我的打招呼'}).status_code, 200)
                    self.assertEqual(client.get('/api/sessions').json()['sessions'][0]['title'], '我的打招呼')
                finally:
                    release.set()
                    registry.wait()
                    registry.delete(identifier)
                    runtime.worker.join(5)

    def test_list_uses_summaries_without_reconstructing_conversations(self):
        with tempfile.TemporaryDirectory() as directory:
            config = replace(load(), approval_mode="full_access", storage_dir=Path(directory), mcp={})
            registry = SessionRegistry(config)
            runtime = registry.create()
            runtime.session.events.append('turn.started', prompt='list title', images=[])
            try:
                with patch.object(web, 'registry', registry), patch.object(web, 'session_store', registry.store), \
                     patch('agent.web.app.EventLog', side_effect=AssertionError('list must not load full history')), \
                     patch('agent.web.app.restore_display_messages', side_effect=AssertionError('list must not restore messages')), \
                     TestClient(web.app) as client:
                    item = client.get('/api/sessions').json()['sessions'][0]
                    self.assertEqual(item['title'], 'list title')
                    self.assertFalse(item['empty'])
                    self.assertIsNone(runtime._agent)
                    self.assertIsNone(runtime._state)
                    runtime.busy = True
                    self.assertEqual(client.get('/api/sessions').json()['sessions'][0]['status'], 'running')
                    runtime.busy = False
            finally:
                runtime.busy = False
                registry.delete(runtime.session.id)
                runtime.worker.join(5)

    def test_status_queries_do_not_start_inference_and_keep_independent_cursors(self):
        with tempfile.TemporaryDirectory() as directory:
            config = replace(load(), approval_mode="full_access", storage_dir=Path(directory), mcp={})
            registry = SessionRegistry(config)
            with patch.object(web, 'registry', registry), patch.object(web, 'session_store', registry.store), TestClient(web.app) as client:
                identifier = client.post('/api/sessions').json()['id']
                monitor = registry.monitor(identifier)
                monitor.update('bash:example', kind='bash', status='running')
                path = f'/api/sessions/{identifier}/watch'
                snapshot = client.get(path).json()
                self.assertEqual(snapshot['changes'][0]['kind'], 'bash')
                monitor.update('bash:example', kind='bash', status='completed', result_path='/tmp/output.log')
                query = f'{path}?cursor={snapshot["cursor"]}'
                self.assertEqual(client.get(query).json(), client.get(query).json())
                self.assertEqual(client.get(path + '?cursor=999').status_code, 400)
                self.assertEqual(client.get(path + '?timeout=200').status_code, 422)
                self.assertIsNone(registry.get(identifier)._agent)
                self.assertEqual(registry.get(identifier).session.events.read(), [])
                self.assertEqual(client.delete(f'/api/sessions/{identifier}').status_code, 200)


if __name__ == '__main__':
    unittest.main()

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.core.session_registry import SessionRegistry
from agent.web import app as web
from agent.workflow.config import load


class SessionApiTests(unittest.TestCase):
    def test_model_switch_changes_state_without_initializing_mcp_or_model_clients(self):
        with tempfile.TemporaryDirectory() as directory:
            config = replace(load(), event_log=Path(directory) / 'events.jsonl', mcp={'offline': 'http://127.0.0.1:1/mcp'})
            registry = SessionRegistry(config)
            with patch.object(web, 'registry', registry), patch.object(web, 'session_store', registry.store), TestClient(web.app) as client:
                identifier = client.post('/api/sessions').json()['id']
                path = f'/api/sessions/{identifier}'
                runtime = registry.get(identifier)
                selected = runtime.state['model']
                with patch('agent.core.session_registry.McpClient', side_effect=AssertionError('MCP must stay disconnected')), \
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

    def test_status_queries_do_not_start_inference_and_keep_independent_cursors(self):
        with tempfile.TemporaryDirectory() as directory:
            config = replace(load(), event_log=Path(directory) / 'events.jsonl', mcp={})
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

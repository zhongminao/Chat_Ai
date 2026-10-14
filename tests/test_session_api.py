import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.core.session_runtime import SessionRuntimes
from agent.model.protocol import ModelChunk
from agent.web import app as web
from agent.workflow.config import load


class SessionApiTests(unittest.TestCase):
    def test_parent_child_metadata_read_only_child_and_deletion_order(self):
        with tempfile.TemporaryDirectory() as directory:
            config = replace(load(), event_log=Path(directory) / 'events.jsonl', mcp={})
            registry = SessionRuntimes(config)
            with patch.object(web, 'registry', registry), patch.object(web, 'session_store', registry.store), \
                 patch('agent.model.catalog.ModelCatalog.runtime', return_value=(object(), object())), \
                 patch('agent.core.agent_runtime.stream', return_value=iter([ModelChunk(content='hello')])), \
                 TestClient(web.app) as client:
                parent_id = client.post('/api/sessions').json()['id']
                parent = registry.get(parent_id)
                child_id = json.loads(parent.delegate('child', 'work'))['session_id']
                registry.wait()
                listing = client.get('/api/sessions').json()['sessions']
                child = next(item for item in listing if item['id'] == child_id)
                self.assertEqual(child['parent_session_id'], parent_id)
                self.assertEqual(child['status'], 'failed')
                snapshot = client.get(f'/api/sessions/{child_id}/conversation').json()
                self.assertEqual(snapshot['parent_session_id'], parent_id)
                self.assertFalse(snapshot['busy'])
                self.assertEqual(client.post(f'/api/sessions/{child_id}/messages', json={'content': 'again'}).status_code, 400)
                self.assertEqual(client.delete(f'/api/sessions/{parent_id}').status_code, 409)
                self.assertEqual(client.delete(f'/api/sessions/{child_id}').status_code, 200)
                self.assertEqual(client.delete(f'/api/sessions/{parent_id}').status_code, 200)
                self.assertEqual(client.get(f'/api/sessions/{parent_id}/conversation').status_code, 404)
                for runtime in registry.items.values():
                    runtime.queue.put(None)
                    runtime.worker.join(5)


if __name__ == '__main__':
    unittest.main()

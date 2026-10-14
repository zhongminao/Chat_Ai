import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.core.session_registry import SessionRuntimes
from agent.web import app as web
from agent.workflow.config import load


class WatchApiTests(unittest.TestCase):
    def test_status_queries_do_not_start_inference_and_keep_independent_cursors(self):
        with tempfile.TemporaryDirectory() as directory:
            config = replace(load(), event_log=Path(directory) / 'events.jsonl', mcp={})
            registry = SessionRuntimes(config)
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

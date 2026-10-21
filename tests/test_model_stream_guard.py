"""An endlessly emitting provider must fail a child rather than fill its event log."""
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from agent.core.session_registry import SessionRegistry
from agent.model.protocol import ModelChunk, ToolCallDelta
from agent.model.stream_guard import ModelStreamGuard
from agent.workflow.config import load


class ModelStreamGuardTests(unittest.TestCase):
    def test_runaway_child_is_failed_and_visible_to_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            registry = SessionRegistry(replace(load(), storage_dir=Path(temp), workspace=Path(temp), mcp={}))
            root = registry.create()
            child = registry.create(parent_session_id=root.session.id)
            limit = ModelStreamGuard.MAX_TOOL_DELTAS
            emitted = 0

            def runaway(*args, **kwargs):
                nonlocal emitted
                for _ in range(limit * 3):
                    emitted += 1
                    yield ModelChunk(tool_deltas=(ToolCallDelta(index=0, id='call',
                                                                name='submit', arguments='x'),))

            try:
                with patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())), \
                     patch('agent.core.agent_runtime.stream', side_effect=runaway):
                    child.start('runaway')
                    registry.wait()
                self.assertEqual(emitted, limit + 1)
                records = child.session.events.read()
                self.assertEqual(sum(event['type'] == 'tool_call.delta' for event in records), limit)
                self.assertIn('safety budget', next(event['reason'] for event in records
                                                    if event['type'] == 'turn.failed'))
                status = next(item for item in registry.monitor(root.session.id).watch()['changes']
                              if item['id'] == f'agent:{child.session.id}')
                self.assertEqual(status['status'], 'failed')
                self.assertIn('safety budget', status['error'])
            finally:
                for runtime in registry.items.values():
                    runtime.queue.put(None)
                    runtime.worker.join(5)
                registry.store.database.close()

    def test_large_unicode_delta_fails_before_logging(self):
        guard = ModelStreamGuard()
        with self.assertRaisesRegex(RuntimeError, 'safety budget'):
            guard.check(ToolCallDelta(arguments='界' * 23000))
        self.assertEqual(guard.tool_deltas, 1)

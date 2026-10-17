"""A failed MCP service cannot take down other tools or ordinary turns."""
import asyncio
import json
import tempfile
import threading
import time
import unittest
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from mcp import types

from agent.core.session_registry import SessionRegistry
from agent.model.protocol import ModelChunk, ToolCallDelta
from agent.tools.mcp.client import McpClient
from agent.tools.router import ToolRouter
from agent.workflow.config import load


class McpResilienceTests(unittest.TestCase):
    def test_discovery_failure_only_removes_that_servers_tools(self):
        healthy = types.Tool(name="ping", description="test tool", input_schema={"type": "object"})
        with patch.object(McpClient, "_list", side_effect=[OSError("offline"), [healthy]]), \
             self.assertLogs("agent.tools.mcp.client", level="WARNING") as logs:
            client = McpClient({"offline": "http://offline", "healthy": "http://healthy"})
        self.assertEqual(list(client.tools), ["mcp_healthy_ping"])
        self.assertEqual([s["function"]["name"] for s in client.schemas], ["mcp_healthy_ping"])
        self.assertIn("offline", logs.output[0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.txt").write_text("local tools still work")
            router = ToolRouter(root, client)
            self.assertIn("local tools still work", router.call("read_file", {"path": "sample.txt"}))
            with patch.object(client, "call", return_value=types.CallToolResult(content=[
                    types.TextContent(type="text", text="pong")])):
                self.assertEqual(router.call("mcp_healthy_ping", {}), "pong")
            with patch.object(client, "call", side_effect=OSError("disconnected after discovery")):
                self.assertIn("[mcp error]", router.call("mcp_healthy_ping", {}))
            self.assertIn("local tools still work", router.call("read_file", {"path": "sample.txt"}))

    def test_discovery_timeout_closes_the_connection_attempt(self):
        closed = threading.Event()

        @asynccontextmanager
        async def never_connect(url):
            try:
                await asyncio.Event().wait()
                yield
            finally:
                closed.set()

        started = time.monotonic()
        with patch("agent.tools.mcp.client.streamable_http_client", never_connect), \
             self.assertLogs("agent.tools.mcp.client", level="WARNING"):
            client = McpClient({"offline": "http://offline"})
        self.assertEqual(client.schemas, [])
        self.assertTrue(closed.is_set())
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.9)
        self.assertLess(elapsed, 1.5)

    def test_unregistered_tools_return_receipts_without_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            router = ToolRouter(Path(directory))
            with patch('agent.tools.router.execute') as execute:
                for name in ['mcp_offline_read_file', 'unknown_tool', 'delegate', 'watch']:
                    with self.subTest(name=name):
                        result = router.call(name, {})
                        self.assertEqual(result, f'[tool error] 当前工具不可用：{name}')
                execute.assert_not_called()

    def test_retrying_a_historical_unregistered_tool_does_not_end_the_turn(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sample.txt').write_text('local result')
            config = replace(load(), approval_mode="full_access", workspace=root, storage_dir=root,
                             mcp={'offline': 'http://offline'}, max_rounds=2)
            registry = SessionRegistry(config)
            session = registry.create()

            def model(client, name, messages, schemas, **kwargs):
                self.assertNotIn('mcp_offline_read_file', [s['function']['name'] for s in schemas])
                if messages[-1]['role'] == 'user':
                    yield ModelChunk(tool_deltas=(
                        ToolCallDelta(index=0, id='missing', name='mcp_offline_read_file', arguments='{}'),
                        ToolCallDelta(index=1, id='local', name='read_file', arguments=json.dumps({'path': 'sample.txt'})),
                    ))
                else:
                    self.assertIn('当前工具不可用', messages[-2]['content'])
                    self.assertEqual(messages[-1]['content'], 'local result')
                    yield ModelChunk(content='continued after unavailable tool')

            try:
                with patch.object(McpClient, '_list', side_effect=OSError('offline')), \
                     self.assertLogs('agent.tools.mcp.client', level='WARNING'), \
                     patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())), \
                     patch('agent.core.agent_runtime.stream', side_effect=model):
                    session.agent.state['messages'].extend([
                        {'role': 'user', 'content': 'old request'},
                        {'role': 'assistant', 'content': '', 'tool_calls': [{
                            'id': 'historical', 'type': 'function', 'function': {
                                'name': 'mcp_offline_read_file', 'arguments': '{}'}}]},
                        {'role': 'tool', 'tool_call_id': 'historical', 'content': 'old observation'},
                    ])
                    session.enqueue('continue')
                    registry.wait()
                records = session.session.events.read()
                self.assertFalse(any(e['type'] == 'turn.failed' for e in records))
                receipts = [e for e in records if e['type'] == 'tool.completed']
                self.assertEqual([e['callId'] for e in receipts], ['missing', 'local'])
                self.assertIn('当前工具不可用', receipts[0]['result'])
                self.assertEqual(session.state['execution']['status'], 'completed')
            finally:
                session.stop()
                registry.wait()
                session.queue.put(None)
                session.worker.join(5)

    def test_all_servers_unavailable_still_allows_a_normal_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(load(), approval_mode="full_access", workspace=root, storage_dir=root,
                             mcp={"offline": "http://offline"})
            registry = SessionRegistry(config)
            session = registry.create()
            try:
                with patch.object(McpClient, "_list", side_effect=OSError("offline")), \
                     self.assertLogs("agent.tools.mcp.client", level="WARNING"), \
                     patch("agent.model.catalog.ModelCatalog.get_binding", return_value=(object(), object())), \
                     patch("agent.core.agent_runtime.stream", return_value=iter([ModelChunk(content="hello")])):
                    session.enqueue("hello")
                    registry.wait()
                self.assertEqual(session.state["execution"]["status"], "completed")
                self.assertEqual(session.state["messages"][-1]["content"], "hello")
                self.assertIn("read_file", [s["function"]["name"] for s in session.agent.tools.schemas])
            finally:
                session.stop()
                registry.wait()
                session.queue.put(None)
                session.worker.join(5)

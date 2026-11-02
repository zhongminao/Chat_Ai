"""Explicit MCP URL discovery keeps the current tool-call batch unchanged."""
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from mcp import types
from agent.agentsessionstate.config import load
from agent.core.session_registry import SessionRegistry
from agent.model.protocol import ModelChunk, ToolCallDelta
from agent.tools.approval import requires_approval
from agent.tools.mcp.client import McpClient
from agent.tools.router import ToolRouter


class LiveMcpTests(unittest.TestCase):
    def test_connect_real_server_then_call_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            url = f'http://127.0.0.1:{port}/mcp'
            script = root / 'fixture.py'
            script.write_text(
                "from mcp.server.mcpserver import MCPServer\n"
                "server = MCPServer('fixture')\n"
                "@server.tool()\n"
                "def ping() -> str:\n"
                "    return 'live-pong'\n"
                f"server.run(transport='streamable-http', host='127.0.0.1', port={port}, "
                "stateless_http=True, json_response=True)\n"
            )
            with (root / 'server.log').open('wb') as output:
                process = subprocess.Popen([sys.executable, str(script)], stdout=output, stderr=subprocess.STDOUT)
            config = replace(load(), approval_mode='full_access', workspace=root,
                             storage_dir=root / 'storage', mcp={})
            registry = SessionRegistry(config)
            session = registry.create()
            try:
                for _ in range(200):
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                            break
                    except OSError:
                        self.assertIsNone(process.poll(), (root / 'server.log').read_text(errors='replace'))
                        time.sleep(0.05)
                def model(client, name, messages, schemas, **kwargs):
                    if messages[-1]['role'] == 'user':
                        yield ModelChunk(tool_deltas=(ToolCallDelta(
                            index=0, id='connect', name='enable_mcp',
                            arguments='{"url": "' + url + '"}'),))
                    else:
                        self.assertTrue(any(item['function']['name'].endswith('_ping') for item in schemas))
                        yield ModelChunk(content='connected')

                with patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())), \
                     patch('agent.core.agent_runtime.stream', side_effect=model):
                    session.enqueue('connect ' + url)
                    registry.wait()
                router = session.agent.tools
                name = next(name for name in router.mcp.tools if name.endswith('_ping'))
                self.assertIn('live-pong', str(router.call(name, {})))
                self.assertTrue(any(e['type'] == 'mcp.enabled' and e['url'] == url
                                    for e in session.session.events.read()))
                reopened = SessionRegistry(config)
                restored = reopened.get(session.session.id)
                restored_router = restored.agent.tools
                self.assertIn(name, restored_router.mcp.tools)
                self.assertIn('live-pong', str(restored_router.call(name, {})))
                restored.queue.put(None)
                restored.worker.join(5)
            finally:
                session.queue.put(None)
                session.worker.join(5)
                process.terminate()
                process.wait(timeout=10)


class McpEnableTests(unittest.TestCase):
    def test_new_url_retries_failed_discovery_and_does_not_register_early(self):
        ping = types.Tool(name='ping', input_schema={'type': 'object'})
        with tempfile.TemporaryDirectory() as directory, patch.object(McpClient, '_list', side_effect=[OSError('offline'), [ping]]) as listing:
            router = ToolRouter(Path(directory), McpClient({}))
            self.assertIn('OSError', router.call('enable_mcp', {'url': 'http://later/mcp'}))
            self.assertFalse(router.pending_tools)
            self.assertIn('discovered', router.call('enable_mcp', {'url': 'http://later/mcp'}))
            self.assertIn('当前工具不可用', router.call('mcp_dynamic_', {}))
            self.assertEqual(len(router.commit_pending_tools()), 1)
            self.assertEqual(listing.call_count, 2)
            self.assertTrue(any(s['function']['name'].endswith('_ping') for s in router.schemas))
            self.assertIn('already enabled', router.call('enable_mcp', {'url': 'http://later/mcp'}))
            self.assertEqual(listing.call_count, 2)
            self.assertIn('HTTP(S)', router.call('enable_mcp', {'url': 'file:///no'}))
        self.assertTrue(requires_approval('enable_mcp', False))

    def test_default_config_and_new_url_visible_next_model_request_same_turn(self):
        configured = types.Tool(name='configured', input_schema={'type': 'object'})
        ping = types.Tool(name='ping', input_schema={'type': 'object'})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(load(), approval_mode='full_access', workspace=root, storage_dir=root,
                             mcp={'default': 'http://default/mcp'}, max_rounds=3)
            registry = SessionRegistry(config)
            session = registry.create()
            seen = []

            def model(client, name, messages, schemas, **kwargs):
                seen.append([s['function']['name'] for s in schemas])
                if len(seen) == 1:
                    yield ModelChunk(tool_deltas=(
                        ToolCallDelta(index=0, id='enable', name='enable_mcp', arguments='{"url":"http://later/mcp"}'),
                        ToolCallDelta(index=1, id='early', name='mcp_dynamic_missing', arguments='{}'),
                    ))
                else:
                    yield ModelChunk(content='done')

            try:
                with patch.object(McpClient, '_list', side_effect=[[configured], [ping]]), \
                     patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())), \
                     patch('agent.core.agent_runtime.stream', side_effect=model):
                    session.enqueue('Connect http://later/mcp')
                    registry.wait()
                self.assertEqual(len(seen), 2)
                self.assertIn('mcp_default_configured', seen[0])
                self.assertFalse(any(n.endswith('_ping') for n in seen[0]))
                self.assertTrue(any(n.endswith('_ping') for n in seen[1]))
                receipts = [e for e in session.session.events.read() if e['type'] == 'tool.completed']
                self.assertIn('当前工具不可用', receipts[1]['result'])
                self.assertEqual(session.state['execution']['status'], 'completed')
            finally:
                session.stop()
                registry.wait()
                session.queue.put(None)
                session.worker.join(5)


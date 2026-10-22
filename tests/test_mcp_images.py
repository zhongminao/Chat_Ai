"""MCP image ingestion, model messages and existing HTTP search compatibility."""
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

from mcp import types
from PIL import Image

from agent.model.request_messages import build_tool_message, request_messages
from agent.storage.session import SessionStore
from agent.tools.mcp.client import McpClient
from agent.tools.mcp.results import convert_result
from agent.tools.result import ToolResult
from agent.tools.images import read_image, show_image
from agent.tools.router import ToolRouter


def picture(color="red"):
    data = BytesIO()
    Image.new("RGB", (20, 10), color).save(data, format="PNG")
    return types.ImageContent(type="image", data=base64.b64encode(data.getvalue()).decode(), mime_type="image/png")


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.images = SessionStore(self.root).create().images

    def tearDown(self):
        self.directory.cleanup()

    def test_image_reaches_model_and_display_and_deduplicates(self):
        response = types.CallToolResult(content=[types.TextContent(type="text", text="四视图"), picture()])
        result = convert_result(response, self.images, vision=True, max_images=1)
        self.assertIsInstance(result, ToolResult)
        self.assertEqual(result.images, result.model_images)
        self.assertIn("四视图", result.text)
        identifier = result.model_images[0]["id"]
        messages = [{"role": "assistant", "content": "", "tool_calls": [
            {"id": "call1", "type": "function", "function": {"name": "mcp_local_read_image", "arguments": "{}"}}]},
            build_tool_message("call1", result.text, [identifier])]
        outgoing = request_messages(messages, self.images)
        self.assertEqual(outgoing[-1]["role"], "user")
        self.assertTrue(any(item["type"] == "image_url" for item in outgoing[-1]["content"]))
        again = convert_result(response, self.images, vision=True, known_images={identifier}, max_images=1)
        self.assertEqual(again.model_images[0]["id"], identifier)
        self.assertEqual(len(self.images.list()), 1)

    def test_local_read_and_publish_have_compact_receipts(self):
        source = self.root / 'plot.png'
        source.write_bytes(base64.b64decode(picture().data))
        read = read_image(self.root, self.images, str(source))
        self.assertFalse(read.images)
        self.assertIn('尚未向用户展示', read.text)
        self.assertNotIn('来源：', read.text)
        self.assertNotIn('名称：', read.text)
        image = read.model_images[0]
        messages = [{"role": "assistant", "content": "", "tool_calls": [
            {"id": "read", "type": "function", "function": {"name": "read_image", "arguments": "{}"}}]},
            build_tool_message('read', read.text, [image['id']])]
        outgoing = request_messages(messages, self.images)
        self.assertEqual(str(outgoing).count(str(self.images.path(image['id']))), 1)
        published = show_image(self.root, self.images, str(self.images.path(image['id'])))
        self.assertEqual(published.images[0]['id'], image['id'])
        self.assertFalse(published.model_images)
        self.assertIn(self.images.markdown(image), published.text)
        self.assertEqual(len(self.images.list()), 1)

    def test_separate_uploads_of_identical_bytes_keep_distinct_numbers_and_images(self):
        data = base64.b64decode(picture().data)
        first = self.images.add(data, 'same.png')
        second = self.images.add(data, 'same.png')
        self.assertNotEqual(first['id'], second['id'])
        messages = [{"role": "user", "content": "比较图片", "images": [first['id'], second['id']]}]
        content = request_messages(messages, self.images)[0]['content']
        self.assertEqual(sum(part['type'] == 'image_url' for part in content), 2)
        labels = [part['text'] for part in content if part['type'] == 'text']
        self.assertIn(f"图片编号 1\n路径：{self.images.path(first['id'])}", labels)
        self.assertIn(f"图片编号 2\n路径：{self.images.path(second['id'])}", labels)
        repeated = request_messages([*messages, {"role": "user", "content": "再看第一张", "images": [first['id']]}], self.images)
        self.assertFalse(any(part['type'] == 'image_url' for part in repeated[-1]['content']))
        self.assertIn('此前已附图', repeated[-1]['content'][-1]['text'])

    def test_nonvision_model_displays_without_image_input(self):
        result = convert_result(types.CallToolResult(content=[picture()]), self.images)
        self.assertEqual(len(result.images), 1)
        self.assertEqual(result.model_images, [])
        self.assertIn("未启用视觉", result.text)

    def test_budget_checked_before_saving(self):
        response = types.CallToolResult(content=[picture(), picture("blue")])
        with self.assertRaisesRegex(ValueError, "最多包含"):
            convert_result(response, self.images, vision=True, max_images=1)
        self.assertEqual(self.images.list(), [])

    def test_malformed_image_is_reported_by_router(self):
        mcp = Mock()
        mcp.schemas = [{"type": "function", "function": {"name": "mcp_local_read_image", "parameters": {}}}]
        mcp.tools = {"mcp_local_read_image": ("local", "read_image")}
        mcp.call.return_value = types.CallToolResult(content=[
            types.ImageContent(type="image", data="not base64!", mime_type="image/png")])
        router = ToolRouter(self.root, mcp, images=self.images)
        self.assertIn("[mcp error]", router.call("mcp_local_read_image", {}))
        self.assertEqual(self.images.list(), [])

    def test_structured_text_and_errors(self):
        response = types.CallToolResult(content=[types.TextContent(type="text", text="extra")],
                                        structured_content={"ok": True})
        result = convert_result(response, self.images)
        self.assertIn('"ok": true', result)
        self.assertIn("extra", result)
        error = types.CallToolResult(content=[types.TextContent(type="text", text="failed")], is_error=True)
        self.assertEqual(convert_result(error, self.images), "[mcp error] failed")

    def test_structured_json_fallback_is_not_duplicated(self):
        data = {"cwd": "D:\\code", "output": "中文\nresult", "exit_code": 0}
        for fallback in [json.dumps(data, indent=2), json.dumps(data, separators=(",", ":")),
                         json.dumps(data, ensure_ascii=False)]:
            response = types.CallToolResult(content=[types.TextContent(type="text", text=fallback)],
                                           structured_content=data)
            self.assertEqual(convert_result(response, self.images), json.dumps(data, ensure_ascii=False))

    def test_router_reaches_converter(self):
        mcp = Mock()
        mcp.schemas = [{"type": "function", "function": {"name": "mcp_local_read_image", "parameters": {}}}]
        mcp.tools = {"mcp_local_read_image": ("local", "read_image")}
        mcp.call.return_value = types.CallToolResult(content=[picture()])
        router = ToolRouter(self.root, mcp, images=self.images)
        router.vision = True
        router.image_limit = 8
        result = router.call("mcp_local_read_image", {"path": "D:/example.png"})
        self.assertEqual(len(result.model_images), 1)

    @unittest.skipUnless(os.getenv("CHAT_AI_TEST_SEARCH"), "set CHAT_AI_TEST_SEARCH=1 for live search smoke test")
    def test_existing_search_over_http(self):
        runtime = McpClient({"web": "http://127.0.0.1:8766/mcp"})
        self.assertIn("mcp_web_search", runtime.tools)
        response = runtime.call("mcp_web_search", {"query": "injection molding", "limit": 1})
        self.assertIsInstance(response, types.CallToolResult)
        result = convert_result(response, self.images)
        self.assertIsInstance(result, str)
        self.assertTrue(result)

    def test_image_over_http_reaches_model_message(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        block = picture()
        script = self.root / "image_server.py"
        script.write_text(
            "from mcp import types\nfrom mcp.server.mcpserver import MCPServer\n"
            "server = MCPServer('fixture')\n"
            "@server.tool(structured_output=False)\n"
            "def read_image():\n"
            f"    return [types.ImageContent(type='image', data={block.data!r}, mime_type='image/png')]\n"
            f"server.run(transport='streamable-http', host='127.0.0.1', port={port}, stateless_http=True, json_response=True)\n")
        server_log = self.root / 'image_server.log'
        with server_log.open('wb') as output:
            process = subprocess.Popen([sys.executable, str(script)], stdout=output, stderr=subprocess.STDOUT)
        try:
            # Fixture startup may include cold imports; production discovery still has its 1s limit.
            for _ in range(600):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    if process.poll() is not None:
                        self.fail("fixture MCP server exited")
                    time.sleep(0.05)
            for _ in range(3):
                self.assertIsNone(process.poll(), server_log.read_text(errors='replace')[-3000:])
                ready = McpClient({'local': f'http://127.0.0.1:{port}/mcp'})
                if 'mcp_local_read_image' in ready.tools:
                    break
            self.assertIn('mcp_local_read_image', ready.tools, server_log.read_text(errors='replace')[-3000:])
            with socket.socket() as offline:
                offline.bind(("127.0.0.1", 0))
                offline_port = offline.getsockname()[1]
            with self.assertLogs("agent.tools.mcp.client", level="WARNING"):
                runtime = McpClient({"offline": f"http://127.0.0.1:{offline_port}/mcp",
                                     "local": f"http://127.0.0.1:{port}/mcp"})
            router = ToolRouter(self.root, runtime, images=self.images)
            router.vision = True
            result = router.call("mcp_local_read_image", {})
            self.assertIsInstance(result, ToolResult)
            identifier = result.model_images[0]["id"]
            self.assertEqual(self.images.path(identifier).read_bytes(), base64.b64decode(block.data))
            outgoing = request_messages([build_tool_message("call1", result.text, [identifier])], self.images)
            self.assertTrue(any(part["type"] == "image_url" for part in outgoing[-1]["content"]))
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()

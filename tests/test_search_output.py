import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from mcp import types

from agent.tools.result import ToolResult
from agent.tools.router import ToolRouter
from agent.tools.search_output import extract_context, web_search_output


class SearchOutputTests(unittest.TestCase):
    def test_window_defaults_to_200_and_can_be_overridden(self):
        text = "左" * 400 + "vrma" + "右" * 400
        matched, excerpt = extract_context(text, ["vrma"])
        self.assertEqual(matched, ["vrma"])
        self.assertEqual(excerpt, "…" + "左" * 200 + "vrma" + "右" * 200 + "…")
        self.assertEqual(extract_context(text, ["vrma"], 20)[1],
                         "…" + "左" * 20 + "vrma" + "右" * 20 + "…")

    def test_sentence_extension_is_bounded(self):
        text = "旧句。前文vrma后文。新句"
        self.assertEqual(extract_context(text, ["vrma"], 1)[1], "…前文vrma后文。…")
        text = "x" * 500 + "vrma" + "y" * 500
        self.assertLessEqual(len(extract_context(text, ["vrma"], 20)[1]), 46)

    def test_web_window_changes_only_excerpts_and_keeps_original(self):
        raw = json.dumps({"results": [{"url": "https://example.com", "title": "VRMA",
                                       "content": "x" * 400 + "vrma" + "y" * 400}]})
        short = web_search_output(raw, "vrma", context_chars=20)
        long = web_search_output(raw, "vrma", context_chars=220)
        self.assertIsInstance(short, ToolResult)
        self.assertEqual(short.text, raw)
        self.assertEqual(short.sections[0].body, long.sections[0].body)
        self.assertGreater(len(long.sections[0].summary), len(short.sections[0].summary))
        self.assertEqual(web_search_output("unrecognized", "vrma"), "unrecognized")

    def test_router_applies_window_locally_without_sending_it_to_mcp(self):
        mcp = Mock()
        mcp.schemas = [{"type": "function", "function": {"name": "mcp_web_search"}}]
        mcp.tools = {"mcp_web_search": ("web", "search")}
        mcp.call.return_value = types.CallToolResult(content=[], structured_content={
            "results": [{"url": "https://example.com", "content": "x" * 400 + "vrma" + "y" * 400}],
        })
        router = ToolRouter(Path("."), mcp, web_search_config={"context_chars": 20})
        output = router.call("mcp_web_search", {"query": "vrma"})
        self.assertIn("…" + "x" * 20 + "vrma" + "y" * 20 + "…", output.sections[0].summary)
        mcp.call.assert_called_once_with("mcp_web_search", {"query": "vrma"}, None)

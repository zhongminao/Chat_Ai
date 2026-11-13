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
        mcp.call.assert_called_once_with("mcp_web_search", {"query": "vrma", "limit": 50}, None)

    def test_web_all_results_kept_with_separate_briefs(self):
        rows = [{"url": f"https://example.com/{i}", "title": f"Title {i}",
                 "content": "Weather is mild. The residual policy corrects joint PD targets.",
                 "summary": "Generated summary must not be quoted."} for i in range(50)]
        raw = json.dumps({"backend": "deepseek", "results": rows})
        output = web_search_output(raw, "residual policy PD", detail_limit=6)
        self.assertEqual(output.text, raw)
        self.assertEqual(output.detail_limit, 6)
        self.assertEqual(len(output.sections), 50)
        self.assertIn("非模型总结", output.sections[-1].brief)
        self.assertNotIn("Generated summary", output.sections[-1].brief)
        self.assertIn("Generated summary", output.sections[-1].body)

    def test_router_limit_controls_local_details_for_both_backends(self):
        for enhanced in [False, True]:
            with self.subTest(enhanced=enhanced):
                mcp = Mock()
                schema = {"type": "function", "function": {
                    "name": "mcp_web_search", "description": "old",
                    "parameters": {"properties": {"limit": {"type": "integer", "default": 5}}}}}
                mcp.schemas = [schema]
                mcp.tools = {"mcp_web_search": ("web", "search")}
                mcp.call.return_value = types.CallToolResult(content=[], structured_content={
                    "results": [{"url": f"https://example.com/{i}", "content": "Policy control."}
                                for i in range(50)]})
                router = ToolRouter(Path("."), mcp)
                args = {"query": "policy", "limit": 6, "enhanced": enhanced}
                output = router.call("mcp_web_search", args)
                mcp.call.assert_called_once_with("mcp_web_search", {**args, "limit": 50}, None)
                self.assertEqual(args["limit"], 6)
                self.assertEqual(len(output.sections), 50)
                self.assertEqual(output.detail_limit, 6)
                description = next(s["function"]["description"] for s in router.schemas
                                   if s["function"]["name"] == "mcp_web_search")
                self.assertIn("limit 只控制", description)
                self.assertEqual(schema["function"]["description"], "old")

    def test_router_rejects_invalid_detail_limit_without_calling_backend(self):
        for limit in [0, 51, True, "6"]:
            mcp = Mock()
            mcp.schemas = [{"type": "function", "function": {"name": "mcp_web_search"}}]
            mcp.tools = {"mcp_web_search": ("web", "search")}
            router = ToolRouter(Path("."), mcp)
            result = router.call("mcp_web_search", {"query": "policy", "limit": limit})
            self.assertIn("limit", result)
            mcp.call.assert_not_called()

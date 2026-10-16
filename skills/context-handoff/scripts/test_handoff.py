import copy
import json
from pathlib import Path
import tempfile
import unittest

from handoff import group_messages, pack, write_json, read_json


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.file = self.root / "engine.cjs"
        self.file.write_text("first\nsecond\nthird\n", encoding="utf-8")
        self.users = [{"seq": 1, "content": "保留原文：\\n不是换行\n后续要求以此为准。"}]
        self.messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": self.users[0]["content"]},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "a", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
                {"id": "b", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "b", "content": "B"},
            {"role": "tool", "tool_call_id": "a", "content": "A"},
            {"role": "assistant", "content": "done"},
        ]
        self.snapshot = {
            "source_session_id": "source", "source_seq": 7, "source_events_sha256": "hash",
            "workspace": str(self.root), "model": {"name": "qwen"},
            "messages": self.messages, "users": self.users,
            "groups": group_messages(self.messages),
        }
        self.plan = {"version": 1, "summary": "已完成引擎；下一步完善界面。",
                     "keep_groups": ["g0001"],
                     "files": [{"path": "engine.cjs", "start_line": 2, "end_line": 3}]}

    def test_tool_call_and_all_replies_are_indivisible(self):
        self.assertEqual(len(self.snapshot["groups"]), 2)
        self.assertEqual(len(self.snapshot["groups"][0]["messages"]), 3)
        for broken in (self.messages[:4], self.messages[:3] + self.messages[5:]):
            with self.assertRaises(ValueError):
                group_messages(broken)

    def test_frozen_bundle_preserves_user_and_selected_file_exactly(self):
        original = copy.deepcopy(self.snapshot)
        bundle = pack(self.snapshot, self.plan, "继续任务")
        path = self.root / "bundle.json"
        write_json(path, bundle)
        self.file.write_text("changed\n", encoding="utf-8")
        restored = read_json(path)
        self.assertEqual(restored["context"]["user_inputs_verbatim"], self.users)
        self.assertEqual(restored["context"]["current_file_snapshots"][0]["content"], "second\nthird\n")
        self.assertEqual(restored["messages"], bundle["messages"])
        self.assertEqual(self.snapshot, original)
        self.assertEqual(json.loads(restored["messages"][1]["content"].split("\n\n", 1)[1]), restored["context"])

    def test_unknown_group_and_invalid_ranges_fail_without_truncating(self):
        for change in ({"keep_groups": ["g9999"]}, {"keep_groups": ["g0001", "g0001"]},
                       {"files": [{"path": "engine.cjs", "start_line": 1, "end_line": 4}]},
                       {"files": [{"path": "engine.cjs", "start_line": 0, "end_line": 2}]}):
            with self.assertRaises(ValueError):
                pack(self.snapshot, {**self.plan, **change}, "continue")
        with self.assertRaises(ValueError):
            pack(self.snapshot, self.plan, "continue", max_chars=20)

    def test_paths_cannot_escape_workspace(self):
        for path in ("../outside", str(self.file.resolve())):
            with self.assertRaises(ValueError):
                pack(self.snapshot, {**self.plan, "files": [
                    {"path": path, "start_line": 1, "end_line": 1}]}, "continue")
        outside = self.root.parent / (self.root.name + "-outside")
        outside.write_text("private", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        link = self.root / "link"
        link.symlink_to(outside)
        with self.assertRaises(ValueError):
            pack(self.snapshot, {**self.plan, "files": [
                {"path": "link", "start_line": 1, "end_line": 1}]}, "continue")


if __name__ == "__main__":
    unittest.main()

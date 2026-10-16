"""Context boundaries, durable replay and the shared CLI/Web event contract."""
import copy
import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from agent.cli.output import render_context_event
from agent.core.agent_factory import build_state
from agent.core.session_registry import SessionRegistry
from agent.model.protocol import ModelChunk, ToolCallDelta
from agent.model.tokens import count_request_tokens
from agent.model.context_summary import summarize_context
from agent.core.cancellation import CancellationToken, ExecutionContext
from agent.workflow import context_compaction
from agent.workflow.config import load
from agent.workflow.message_replay import restore_display_messages, restore_model_messages


def tool_pair(content="observation"):
    return [{"role": "assistant", "content": "", "tool_calls": [
        {"id": "call", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
    ]}, {"role": "tool", "tool_call_id": "call", "content": content}]


class CompactionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = {"enabled": True, "trigger_tokens": 100}
        self.state = {"messages": [{"role": "system", "content": "system"},
            {"role": "user", "content": "old task"}, *tool_pair("old results"),
            {"role": "user", "content": "latest task", "images": ["image-id"]}, *tool_pair()]}

    def test_pure_update_preserves_latest_user_images_and_whole_tool_group(self):
        original = copy.deepcopy(self.state)
        selected = context_compaction.plan(self.state, 100, self.config)
        update = context_compaction.build_update(selected, "Known facts; unfinished work.")
        self.assertEqual(self.state, original)
        self.assertEqual(update["messages"][0], original["messages"][0])
        self.assertEqual(update["messages"][2:], original["messages"][-3:])
        self.assertEqual(selected["history"], original["messages"][1:4])

    def test_can_compact_a_long_single_user_tool_loop(self):
        self.state["messages"].pop(4)
        selected = context_compaction.plan(self.state, 150, self.config)
        self.assertEqual(selected["retained"][0]["content"], "old task")
        self.assertEqual(selected["history"], tool_pair("old results"))

    def test_disabled_under_threshold_empty_summary_and_unshrinkable_input(self):
        self.assertIsNone(context_compaction.plan(self.state, 99, self.config))
        self.assertIsNone(context_compaction.plan(self.state, 100, {"enabled": False}))
        with self.assertRaises(ValueError):
            context_compaction.build_update({}, " ")
        with self.assertRaises(ValueError):
            context_compaction.plan({"messages": self.state["messages"][:2]}, 100, self.config)
        with self.assertRaises(ValueError):
            context_compaction.validate_compacted_size(150, 100, self.config)
        with self.assertRaises(ValueError):
            context_compaction.validate_compacted_size(50, 60, self.config)

    def test_task_sized_context_can_exceed_the_old_fixed_target(self):
        context_compaction.validate_compacted_size(112000, 50000, {"trigger_tokens": 110592})
        context_compaction.validate_compacted_size(150, 70, self.config)

    def test_estimate_includes_tools_and_does_not_count_image_base64(self):
        messages = [{"role": "user", "content": "hello"}]
        plain = count_request_tokens(None, messages, [], None)
        self.assertGreater(count_request_tokens(None, messages, [{"schema": "x" * 1000}], None), plain)
        self.assertGreater(count_request_tokens(None, [{**messages[0], "images": ["id"]}], [], None), plain + 4000)

    def test_checkpoint_replay_is_exact_and_full_history_is_unchanged(self):
        saved = context_compaction.build_update(context_compaction.plan(self.state, 100, self.config), "summary")["messages"]
        events = [{"type": "turn.started", "prompt": "original user"},
                  {"type": "context.compacted", "messages": saved}]
        self.assertEqual(restore_model_messages(events, saved[0]), saved)
        changed = {"role": "system", "content": "changed"}
        self.assertEqual(restore_model_messages(events, changed), [changed, *saved[1:]])
        self.assertEqual(restore_display_messages(events)[0]["content"], "original user")
        later = [{"type": "model.started"}, {"type": "message.delta", "text": "continued"},
                 {"type": "model.completed"}]
        self.assertEqual(restore_model_messages(events + later, {})[-1]["content"], "continued")
        newer = [{"role": "system", "content": "new"}, {"role": "user", "content": "new snapshot"}]
        self.assertEqual(restore_model_messages(events + later + [{"type": "context.compacted", "messages": newer}], newer[0]), newer)

    def test_cli_only_renders_context_status(self):
        output = io.StringIO()
        with redirect_stdout(output):
            for kind in ["context.compaction.started", "context.compacted", "message.delta"]:
                render_context_event({"type": kind})
        self.assertIn("正在自动压缩上下文", output.getvalue())
        self.assertIn("上下文已自动压缩", output.getvalue())
        self.assertNotIn("message.delta", output.getvalue())

    def test_summary_is_one_tool_free_request_and_rejects_truncation(self):
        config = load().context
        context = ExecutionContext(CancellationToken())
        selected = context_compaction.plan(self.state, 100, self.config)
        with patch("agent.model.context_summary.stream", return_value=iter([ModelChunk(content="summary", finish_reason="stop")])) as request:
            self.assertEqual(summarize_context(None, "model", None, selected, config, context), "summary")
            args, kwargs = request.call_args
            self.assertEqual(args[3], [])
            self.assertNotIn("max_tokens", kwargs)
            self.assertNotIn("max_completion_tokens", kwargs)
            self.assertIn("history_to_summarize", args[2][1]["content"])
        for reason in ["length", "content_filter", None]:
            with self.subTest(reason=reason), patch("agent.model.context_summary.stream", return_value=iter([ModelChunk(content="truncated", finish_reason=reason)])):
                with self.assertRaises(ValueError):
                    summarize_context(None, "model", None, selected, config, context)

    def test_long_summary_has_no_framework_length_cap(self):
        content = "必要的项目约束与未完成工作。" * 3000
        config = load().context
        self.assertNotIn("target_tokens", config)
        self.assertNotIn("summary_max_tokens", config)
        with patch("agent.model.context_summary.stream", return_value=iter([ModelChunk(content=content, finish_reason="stop")])):
            self.assertEqual(summarize_context(None, "model", None, context_compaction.plan(self.state, 100, self.config),
                                       config, ExecutionContext(CancellationToken())), content)

    def test_config_validates_thresholds_and_prompt_path(self):
        import yaml
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            main = Path(directory) / 'main_agent.md'
            child = Path(directory) / 'child_agent.md'
            main.write_text('main', encoding='utf-8')
            child.write_text('child', encoding='utf-8')
            for context in [
                {"enabled": "yes"}, {"trigger_tokens": 0},
                {"trigger_tokens": True},
                {"enabled": True, "prompt_file": "missing.md"},
            ]:
                path.write_text(yaml.safe_dump({"system_prompt_file": str(main), "child_system_prompt_file": str(child),
                    "providers_file": str(load().providers_file), "context": context}), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, 'context\\.'):
                    load(path)


class CompactionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.config = replace(load(), workspace=root, storage_dir=root, mcp={},
            context={**load().context, "enabled": True, "trigger_tokens": 100})
        self.registry = SessionRegistry(self.config)
        self.binding = patch("agent.model.catalog.ModelCatalog.get_binding", return_value=(object(), object()))
        self.binding.start()
        self.runtime = self.registry.create()
        self.agent = self.runtime.agent
        self.agent.state["messages"].extend([
            {"role": "user", "content": "old"}, {"role": "assistant", "content": "old reply"}])

    def tearDown(self):
        self.runtime.stop()
        self.registry.wait()
        self.runtime.queue.put(None)
        self.runtime.worker.join(5)
        self.binding.stop()
        self.temp.cleanup()

    def test_user_boundary_commits_before_request_and_factory_restores(self):
        def model(*args, **kwargs):
            records = self.runtime.session.events.read()
            checkpoint = next(e for e in records if e["type"] == "context.compacted")
            self.assertEqual(args[2], checkpoint["messages"])
            self.assertEqual(checkpoint["messages"][-1]["content"], "new")
            yield ModelChunk(content="continued")

        with patch("agent.core.agent_runtime.count_request_tokens", side_effect=[150, 50]), \
             patch("agent.core.agent_runtime.summarize_context", return_value="summary") as summary, \
             patch("agent.core.agent_runtime.stream", side_effect=model):
            self.runtime.enqueue("new")
            self.registry.wait()
        summary.assert_called_once()
        records = self.runtime.session.events.read()
        restored = build_state(self.config, {}, records)
        self.assertEqual(restored["messages"], self.agent.state["messages"])
        self.assertEqual(self.agent.state["execution"]["status"], "completed")
        self.assertIn("new", [m.get("content") for m in restore_display_messages(records)])

    def test_compaction_after_whole_tool_batch(self):
        def model(*args, **kwargs):
            if args[2][-1]["role"] == "user":
                yield ModelChunk(tool_deltas=tuple(ToolCallDelta(index=i, id=f"c{i}", name="read_file",
                    arguments=json.dumps({"path": "missing"})) for i in range(2)))
            else:
                yield ModelChunk(content="done")

        with patch("agent.core.agent_runtime.count_request_tokens", side_effect=[50, 150, 50]), \
             patch("agent.core.agent_runtime.summarize_context", return_value="summary"), \
             patch("agent.core.agent_runtime.stream", side_effect=model):
            self.runtime.enqueue("new")
            self.registry.wait()
        records = self.runtime.session.events.read()
        checkpoint = next(e for e in records if e["type"] == "context.compacted")
        self.assertEqual([m["tool_call_id"] for m in checkpoint["messages"] if m["role"] == "tool"], ["c0", "c1"])
        completed = [e["seq"] for e in records if e["type"] == "tool.completed"]
        self.assertLess(max(completed), checkpoint["seq"])
        self.assertEqual(self.agent.state["execution"]["status"], "completed")

    def test_failed_summary_budget_or_persistence_never_replaces_messages(self):
        for failure in ["empty", "budget", "disk"]:
            with self.subTest(failure=failure):
                before = copy.deepcopy(self.agent.state["messages"])
                append = self.runtime.session.events.append
                def save(kind, **kwargs):
                    if kind == "context.compacted" and failure == "disk":
                        raise OSError("disk full")
                    return append(kind, **kwargs)
                with patch("agent.core.agent_runtime.count_request_tokens", side_effect=[150, 110 if failure == "budget" else 50]), \
                     patch("agent.core.agent_runtime.summarize_context", return_value="" if failure == "empty" else "summary"), \
                     patch.object(self.runtime.session.events, "append", side_effect=save):
                    self.runtime.enqueue(failure)
                    self.registry.wait()
                self.assertEqual(self.agent.state["messages"], [*before, {"role": "user", "content": failure}])
                self.assertEqual(self.agent.state["execution"]["status"], "failed")
        kinds = [e["type"] for e in self.runtime.session.events.read()]
        self.assertNotIn("context.compacted", kinds)
        self.assertEqual(kinds.count("context.compaction.failed"), 3)

    def test_stop_during_summary_keeps_messages_and_publishes_cancelled(self):
        entered = threading.Event()
        def summary(*args):
            context = args[-1]
            stopped = threading.Event()
            remove = context.cancellation.add_callback(stopped.set)
            try:
                entered.set()
                self.assertTrue(stopped.wait(5))
                context.cancellation.raise_if_cancelled()
            finally:
                remove()
        with patch("agent.core.agent_runtime.count_request_tokens", return_value=150), \
             patch("agent.core.agent_runtime.summarize_context", side_effect=summary):
            self.runtime.enqueue("new")
            self.assertTrue(entered.wait(3))
            self.runtime.stop()
            self.registry.wait()
        self.assertEqual(self.agent.state["messages"][-1], {"role": "user", "content": "new"})
        kinds = [e["type"] for e in self.runtime.session.events.read()]
        self.assertIn("context.compaction.cancelled", kinds)
        self.assertNotIn("context.compacted", kinds)
        self.assertEqual(self.agent.state["execution"]["status"], "cancelled")

    def test_disabled_makes_no_count_or_summary_requests(self):
        self.agent.context_config = {"enabled": False}
        with patch("agent.core.agent_runtime.count_request_tokens") as counter, \
             patch("agent.core.agent_runtime.summarize_context") as summary, \
             patch("agent.core.agent_runtime.stream", return_value=iter([ModelChunk(content="ok")])):
            self.runtime.enqueue("new")
            self.registry.wait()
        counter.assert_not_called()
        summary.assert_not_called()

    def test_cli_one_shot_consumes_the_same_runtime_events(self):
        from agent.cli.main import main
        channel = self.runtime.bus.subscribe()
        output = io.StringIO()
        with patch('sys.argv', ['chat-ai', 'new', '--session', self.runtime.session.id]), \
             patch('agent.cli.main.load', return_value=self.config), \
             patch('agent.cli.main.SessionRegistry', return_value=self.registry), \
             patch('agent.core.agent_runtime.count_request_tokens', side_effect=[150, 50]), \
             patch('agent.core.agent_runtime.summarize_context', return_value='summary'), \
             patch('agent.core.agent_runtime.stream', return_value=iter([ModelChunk(content='ok')])), \
             redirect_stdout(output):
            main()
        self.assertIn('[正在自动压缩上下文…]', output.getvalue())
        self.assertIn('[上下文已自动压缩]', output.getvalue())
        kinds = []
        while not channel.empty():
            kinds.append(channel.get_nowait()['type'])
        self.assertIn('context.compaction.started', kinds)
        self.assertIn('context.compacted', kinds)

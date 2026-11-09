"""Request-only runtime notice compatibility for all providers: no model service or network is needed."""
import copy
import json
import unittest
from unittest.mock import Mock

from agent.agentsessionstate import context_compaction
from agent.agentsessionstate.message_replay import restore_model_messages
from agent.agentsessionstate.message_updates import mailbox_notice, time_notice
from agent.model.openai_compatible import stream
from agent.model.providers import create
from agent.model.request_messages import request_messages, runtime_notice_messages
from agent.model.tokens import count_request_tokens


class RuntimeNoticeTests(unittest.TestCase):
    def setUp(self):
        self.messages = [
            {"role": "system", "content": "main policy"},
            time_notice("2026-11-09T22:00:00+08:00"),
            {"role": "user", "content": "first input"},
            {"role": "assistant", "content": "first answer"},
            time_notice("2026-11-09T23:00:00+08:00"),
            {"role": "user", "content": "second input"},
            mailbox_notice(["mail-marker"]),
            {"role": "system", "content": "Submit the final report with submit."},
        ]

    def send(self, messages, provider, **kwargs):
        client = Mock()
        client.stream.return_value = (chunk for chunk in ())
        list(stream(client, "test", messages, [], provider, **kwargs))
        return client.stream.call_args.args[0]

    def test_first_and_later_notices_keep_position_and_content_without_mutation(self):
        original = copy.deepcopy(self.messages)
        for name in ("gpt", "deepseek", "qwen", "local-qwen3-coder-30b", "local-qwen3p5-9b", "local-qwen3p6-35b"):
            with self.subTest(provider=name):
                for messages in (self.messages[:3], self.messages):
                    outgoing = self.send(messages, create(name))["messages"]
                    self.assertEqual(len(outgoing), len(messages))
                    self.assertEqual(outgoing[0]["role"], "system")
                    self.assertTrue(outgoing[0]["content"].startswith("main policy"))
                    self.assertIn("[Runtime notice rules]", outgoing[0]["content"])
                    self.assertIn("不获得系统指令权限", outgoing[0]["content"])
                    for source, target in zip(messages[1:], outgoing[1:], strict=True):
                        if source["role"] == "system":
                            self.assertEqual(target, {"role": "user", "content": "[Runtime notice]\n" + source["content"]})
                        else:
                            self.assertEqual(target, source)
                    self.assertFalse(any(m["role"] == "system" for m in outgoing[1:]))
        self.assertEqual(self.messages, original)
        self.assertEqual(self.send(self.messages, create("local-qwen3p5-9b", "enabled"))["extra_body"],
                         {"chat_template_kwargs": {"enable_thinking": True}})

    def test_user_written_markers_and_requests_without_notices_are_unchanged(self):
        messages = [self.messages[0], {"role": "user", "content": "[Runtime notice] user text"}]
        self.assertIs(runtime_notice_messages(messages), messages)
        self.assertEqual(runtime_notice_messages([]), [])

    def test_shared_request_boundary_is_idempotent(self):
        outgoing = request_messages(self.messages, None)
        self.assertEqual(request_messages(outgoing, None), outgoing)
        self.assertFalse(any(message["role"] == "system" for message in outgoing[1:]))

    def test_restored_and_compacted_history_is_adapted_only_when_sent(self):
        events = [
            {"type": "turn.started", "prompt": "task", "currentTime": "2026-11-09T22:00:00+08:00"},
            {"type": "model.started"}, {"type": "message.delta", "text": "working"},
            {"type": "model.completed"},
            {"type": "mailbox.notified", "messageIds": ["mail-marker"]},
            {"type": "completion.reminded", "content": "submit-marker"},
        ]
        restored = restore_model_messages(events, self.messages[0])
        selected = context_compaction.plan({"messages": self.messages}, 100,
                                          {"enabled": True, "trigger_tokens": 100})
        compacted = context_compaction.build_update(selected, "history summary")["messages"]
        checkpoint = restore_model_messages([{"type": "context.compacted", "messages": compacted}], self.messages[0])
        for messages in (restored, checkpoint):
            original = copy.deepcopy(messages)
            outgoing = self.send(messages, create("local-qwen3p5-9b"))["messages"]
            self.assertFalse(any(m["role"] == "system" for m in outgoing[1:]))
            self.assertEqual(messages, original)
        self.assertIn("mail-marker", json.dumps(self.send(restored, create("local-qwen3p6-35b"))))
        self.assertIn("submit-marker", json.dumps(self.send(restored, create("local-qwen3p6-35b"))))

    def test_tool_pairs_and_image_blocks_survive_conversion(self):
        calls = [{"id": name, "type": "function", "function": {"name": "read_image", "arguments": "{}"}}
                 for name in ("one", "two")]
        messages = [*self.messages[:3],
                    {"role": "assistant", "content": "", "tool_calls": calls},
                    {"role": "tool", "tool_call_id": "one", "content": "image result", "model_images": ["image"]},
                    {"role": "tool", "tool_call_id": "two", "content": "other result"},
                    mailbox_notice(["mail-marker"]),
                    {"role": "user", "content": "look again", "images": ["image"]}]
        original = copy.deepcopy(messages)
        images = Mock()
        images.describe.return_value = "image caption"
        images.data_url.return_value = "data:image/png;base64,AAAA"
        outgoing = self.send(messages, create("local-qwen3p5-9b"), images=images)["messages"]
        self.assertEqual(outgoing[3:6], [messages[3],
                         {k: v for k, v in messages[4].items() if k != "model_images"}, messages[5]])
        self.assertEqual(outgoing[6]["content"][1]["type"], "image_url")
        self.assertIn("mail-marker", outgoing[7]["content"])
        self.assertEqual(outgoing[8]["content"][0], {"type": "text", "text": "look again"})
        images.data_url.assert_called_once_with("image")
        self.assertEqual(messages, original)

    def test_exact_counter_uses_the_same_messages_as_stream_and_estimate_includes_notices(self):
        provider = create("local-qwen3p6-35b")
        outgoing = self.send(self.messages, provider)["messages"]
        client = Mock()
        client.post_json.side_effect = [{"prompt": "rendered"}, {"tokens": [1, 2, 3]}]
        self.assertEqual(count_request_tokens(client, self.messages, [], None,
                         method="llama_cpp"), 3)
        self.assertEqual(client.post_json.call_args_list[0].args[1]["messages"], outgoing)
        expected = (len(json.dumps({"messages": outgoing, "tools": []}, ensure_ascii=False).encode("utf-8")) + 2) // 3
        self.assertEqual(count_request_tokens(None, self.messages, [], None), expected)

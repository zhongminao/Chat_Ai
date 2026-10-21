import unittest

from agent.workflow.message_replay import restore_display_messages, restore_model_messages


class MessageReplayTests(unittest.TestCase):
    system = {'role': 'system', 'content': 'system'}

    def test_failed_user_messages_preserve_original_text_and_images(self):
        first = ' A\n原始输入  '
        second = '\nB\n'
        events = [
            {'type': 'turn.started', 'prompt': first, 'images': [{'id': 'image'}]},
            {'type': 'turn.failed', 'reason': 'network unavailable'},
            {'type': 'turn.started', 'prompt': second},
            {'type': 'turn.failed', 'reason': 'network unavailable'},
        ]
        expected = [{'role': 'user', 'content': first, 'images': ['image']},
                    {'role': 'user', 'content': second}]
        for length in [2, 4]:
            with self.subTest(length=length):
                self.assertEqual(restore_model_messages(events[:length], self.system),
                                 [self.system, *expected[:length // 2]])
                self.assertEqual(restore_display_messages(events[:length]), expected[:length // 2])

    def test_compacted_context_and_applied_guidance_keep_consecutive_users(self):
        saved = [self.system, {'role': 'user', 'content': 'summary'}, {'role': 'user', 'content': 'A'}]
        events = [
            {'type': 'turn.started', 'prompt': 'old input'},
            {'type': 'context.compacted', 'messages': saved},
            {'type': 'guidance.applied', 'content': 'guidance', 'images': [{'id': 'image'}]},
            {'type': 'turn.failed', 'reason': 'network unavailable'},
            {'type': 'turn.started', 'prompt': 'B'},
        ]
        self.assertEqual(restore_model_messages(events, self.system), [*saved,
            {'role': 'user', 'content': 'guidance', 'images': ['image']},
            {'role': 'user', 'content': 'B'}])

    def test_cancel_before_model_starts_does_not_reuse_previous_failed_text(self):
        events = [
            {'type': 'turn.started', 'prompt': 'A'},
            {'type': 'model.started'},
            {'type': 'message.delta', 'text': 'unfinished A reply'},
            {'type': 'turn.failed', 'reason': 'connection lost'},
            {'type': 'turn.started', 'prompt': 'B'},
            {'type': 'turn.cancelled', 'answer': ''},
        ]
        expected = [{'role': 'user', 'content': 'A'}, {'role': 'user', 'content': 'B'}]
        self.assertEqual(restore_model_messages(events, self.system), [self.system, *expected])
        self.assertEqual(restore_display_messages(events), expected)

    def test_real_completed_and_cancelled_replies_are_preserved_once(self):
        for terminal in ['model.completed', 'turn.cancelled']:
            with self.subTest(terminal=terminal):
                events = [
                    {'type': 'turn.started', 'prompt': 'A'},
                    {'type': 'model.started'},
                    {'type': 'message.delta', 'text': 'actual reply'},
                    {'type': terminal, 'answer': 'actual reply'},
                    {'type': 'turn.started', 'prompt': 'B'},
                    {'type': 'turn.cancelled', 'answer': ''},
                ]
                self.assertEqual(restore_model_messages(events, self.system), [self.system,
                    {'role': 'user', 'content': 'A'}, {'role': 'assistant', 'content': 'actual reply'},
                    {'role': 'user', 'content': 'B'}])


if __name__ == '__main__':
    unittest.main()

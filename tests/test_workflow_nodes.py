import json
import unittest

from agent.tools.schema import ToolCall
from agent.workflow import messages, transitions


class WorkflowNodeTests(unittest.TestCase):
    def setUp(self):
        self.state = {'model': {'provider': 'test', 'name': 'model', 'thinking': 'disabled'},
                      'messages': [], 'execution': None}

    def apply(self, node, *args):
        original = json.dumps(self.state, sort_keys=True)
        update = node(self.state, *args)
        self.assertEqual(json.dumps(self.state, sort_keys=True), original, 'a node must not mutate its input')
        json.dumps(update, allow_nan=False)
        self.state.update(update)

    def test_nodes_compose_without_runtime_and_keep_input_state_unchanged(self):
        self.apply(transitions.switch_model, {'provider': 'other', 'name': 'new', 'thinking': 'disabled'})
        self.apply(transitions.start, 'run')
        self.apply(messages.receive_user, 'inspect', ['image-id'])
        self.apply(transitions.start_round, 0)
        self.apply(transitions.append_answer, 'Reading ')
        self.apply(transitions.append_answer, 'the file.')
        self.apply(messages.complete_model, self.state['execution']['answer'], [ToolCall('read', 'read_file', {'path': 'x'})])
        self.assertEqual(transitions.after_model(self.state), 'tools')
        self.apply(messages.receive_tool, 'read', 'file contents', ['tool-image'])
        self.assertEqual(transitions.after_tools(self.state), 'model')
        self.apply(transitions.start_round, 1)
        self.apply(transitions.submit, '# Report')
        self.assertEqual(transitions.after_tools(self.state), 'submit')
        self.apply(transitions.report_saved, '# Rendered report', '/reports/run.md')
        self.apply(transitions.complete, '# Rendered report')
        self.assertEqual(transitions.after_model(self.state), 'end')
        self.assertEqual(self.state['execution']['status'], 'completed')
        self.assertEqual(self.state['execution']['report'], '# Rendered report')
        self.assertEqual(self.state['messages'][0]['images'], ['image-id'])
        self.assertEqual(self.state['messages'][-1]['model_images'], ['tool-image'])

    def test_cancel_preserves_partial_text_once_and_does_not_duplicate_tool_requests(self):
        self.apply(transitions.start, 'model-run')
        self.apply(transitions.append_answer, 'partial')
        self.apply(messages.cancel)
        self.apply(messages.cancel)
        self.assertEqual(len(self.state['messages']), 1)
        self.assertEqual(self.state['execution']['status'], 'cancelled')
        self.apply(transitions.start, 'tool-run')
        self.apply(transitions.append_answer, 'run tool')
        self.apply(messages.complete_model, 'run tool', [ToolCall('call', 'run_bash', {'command': 'pwd'})])
        self.apply(messages.cancel)
        self.assertEqual(len(self.state['messages']), 2)
        self.assertEqual(self.state['messages'][-1]['tool_calls'][0]['id'], 'call')

    def test_invalid_operations_leave_state_unchanged(self):
        self.apply(transitions.start, 'run')
        for content in ('', '   ', None):
            with self.subTest(content=content), self.assertRaises(ValueError):
                transitions.submit(self.state, content)
        with self.assertRaises(ValueError):
            transitions.switch_model(self.state, {'provider': 'other', 'name': 'new'})
        self.apply(transitions.submit, 'final')
        with self.assertRaises(ValueError):
            transitions.submit(self.state, 'duplicate')
        self.assertEqual(self.state['execution']['report'], 'final')
        self.apply(transitions.fail, 'delivery failed')
        self.assertEqual(self.state['execution']['error'], 'delivery failed')


if __name__ == '__main__':
    unittest.main()

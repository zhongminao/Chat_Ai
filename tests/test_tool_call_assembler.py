import unittest

from agent.tools.schema import ToolCall, ToolCallAssembler


class ToolCallAssemblerTests(unittest.TestCase):
    def test_full_id_followed_by_empty_deltas(self):
        assembler = ToolCallAssembler()
        assembler.add({'id': 'call_full', 'function': {'name': 'read_file', 'arguments': '{"path":'}})
        for delta in ({}, {'id': None}, {'id': ''}):
            assembler.add(delta)
        assembler.add({'function': {'arguments': '"file.txt"}'}})
        self.assertEqual(assembler.finish(), [ToolCall('call_full', 'read_file', {'path': 'file.txt'})])

    def test_repeated_full_id_does_not_skip_or_duplicate_arguments(self):
        assembler = ToolCallAssembler()
        call_id = 'call_70fce46029244ecc919ba02555484c10'
        # Reproduce a provider repeating the complete ID in all 329 deltas.
        for index, fragment in enumerate(['{"text":"', *['x'] * 327, '"}']):
            assembler.add({'index': 0, 'id': call_id,
                           'function': {'name': 'write_file' if index == 0 else '',
                                        'arguments': fragment}})
        self.assertEqual(assembler.finish(), [ToolCall(call_id, 'write_file', {'text': 'x' * 327})])

    def test_fragmented_id_and_function_name_are_concatenated(self):
        assembler = ToolCallAssembler()
        for call_id, name, arguments in [('call_', 'read_', '{"path":'),
                                         ('abc', 'file', '"file.txt"'), ('123', '', '}')]:
            assembler.add({'id': call_id, 'function': {'name': name, 'arguments': arguments}})
        self.assertEqual(assembler.finish(), [ToolCall('call_abc123', 'read_file', {'path': 'file.txt'})])

    def test_repeated_suffix_fragments_are_not_deduplicated(self):
        assembler = ToolCallAssembler()
        for call_id in ['call_', 'abc', 'abc']:
            assembler.add({'id': call_id})
        self.assertEqual(assembler.finish(), [ToolCall('call_abcabc', '', {})])

    def test_full_id_repeated_after_fragmented_id(self):
        assembler = ToolCallAssembler()
        for call_id in ['call_', 'abc', 'call_abc', 'call_abc']:
            assembler.add({'id': call_id})
        self.assertEqual(assembler.finish(), [ToolCall('call_abc', '', {})])

    def test_interleaved_indexes_keep_independent_ids_and_arguments(self):
        assembler = ToolCallAssembler()
        assembler.add({'index': 2, 'id': 'call_second',
                       'function': {'name': 'second', 'arguments': '{"value":'}})
        assembler.add({'index': 0, 'id': 'call_',
                       'function': {'name': 'first', 'arguments': '{"value":'}})
        assembler.add({'index': 2, 'id': 'call_second', 'function': {'arguments': '2}'}})
        assembler.add({'index': 0, 'id': 'first', 'function': {'arguments': '1}'}})
        self.assertEqual(assembler.finish(), [ToolCall('call_first', 'first', {'value': 1}),
                                             ToolCall('call_second', 'second', {'value': 2})])

    def test_missing_id_keeps_fallback_and_invalid_json_still_raises(self):
        assembler = ToolCallAssembler()
        assembler.add({'index': 3, 'function': {'name': 'empty'}})
        self.assertEqual(assembler.finish(), [ToolCall('call_3', 'empty', {})])
        assembler.add({'index': 3, 'function': {'arguments': '{'}})
        with self.assertRaises(ValueError):
            assembler.finish()


if __name__ == '__main__':
    unittest.main()

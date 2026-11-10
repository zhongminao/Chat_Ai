"""Fine-grained valid code must pass; no-progress streams must never dispatch tools."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from agent.core.session_registry import SessionRegistry
from agent.model.protocol import ModelChunk, ToolCallDelta
from agent.model.stream_guard import ModelStreamGuard
from agent.agentsessionstate.config import load
from agent.tools.schema import ToolCallAssembler


class ModelStreamGuardTests(unittest.TestCase):
    def test_finely_chunked_code_and_repeated_content_are_valid(self):
        expected = {"command": "cat <<'PY'\n" + "    print('你好')\n" * 900 + "PY\n"}
        encoded = json.dumps(expected, ensure_ascii=False)
        self.assertGreater(len(encoded.encode()), 12000)
        for width in [1, 3, 4096, len(encoded)]:
            with self.subTest(width=width):
                guard = ModelStreamGuard()
                assembler = ToolCallAssembler()
                for start in range(0, len(encoded), width):
                    delta = ToolCallDelta(arguments=encoded[start:start + width])
                    guard.check(delta)
                    assembler.add(delta.as_dict())
                self.assertEqual(assembler.finish()[0].arguments, expected)

    def test_fragment_budget_allows_boundary_and_rejects_one_more(self):
        guard = ModelStreamGuard()
        guard.check(ToolCallDelta(arguments='{"text":"'))
        for _ in range(ModelStreamGuard.MAX_TOOL_DELTAS - 1):
            guard.check(ToolCallDelta(arguments='a'))
        self.assertEqual(guard.tool_deltas, 65536)
        with self.assertRaisesRegex(RuntimeError, 'safety budget'):
            guard.check(ToolCallDelta(arguments='a'))

    def test_total_bytes_limit_is_independent_of_fragment_count(self):
        guard = ModelStreamGuard()
        guard.check(ToolCallDelta(arguments='{"text":"'))
        while guard.tool_bytes < guard.MAX_TOOL_BYTES:
            size = min(guard.MAX_SINGLE_DELTA_BYTES, guard.MAX_TOOL_BYTES - guard.tool_bytes)
            guard.check(ToolCallDelta(arguments='x' * size))
        with self.assertRaisesRegex(RuntimeError, 'safety budget'):
            guard.check(ToolCallDelta(arguments='x'))

    def test_large_unicode_delta_fails_before_logging(self):
        guard = ModelStreamGuard()
        with self.assertRaisesRegex(RuntimeError, 'safety budget'):
            guard.check(ToolCallDelta(arguments='界' * 23000))
        self.assertEqual(guard.tool_deltas, 1)

    def test_empty_fragments_are_limited_per_call_despite_other_calls_progressing(self):
        guard = ModelStreamGuard()
        guard.check(ToolCallDelta(index=1, arguments='{"text":"'))
        for _ in range(guard.MAX_EMPTY_DELTAS):
            guard.check(ToolCallDelta(index=0, id='repeated-id'))
            guard.check(ToolCallDelta(index=1, arguments='x'))
        with self.assertRaisesRegex(RuntimeError, 'consecutive empty argument deltas'):
            guard.check(ToolCallDelta(index=0))

    def test_outside_whitespace_limit_does_not_depend_on_chunk_boundaries(self):
        for width in [1, 17, 1024]:
            with self.subTest(width=width):
                guard = ModelStreamGuard()
                for start in range(0, guard.MAX_JSON_WHITESPACE, width):
                    guard.check(ToolCallDelta(arguments=' ' * min(width, guard.MAX_JSON_WHITESPACE - start)))
                guard.check(ToolCallDelta(index=1, arguments='{"other":1}'))
                with self.assertRaisesRegex(RuntimeError, 'whitespace outside JSON strings'):
                    guard.check(ToolCallDelta(arguments='\n'))

    def test_string_whitespace_unicode_and_escaped_quotes_are_not_rejected(self):
        expected = {"text": ' ' * 3000 + '\t\n你好 "quoted" \\ tail'}
        encoded = json.dumps(expected, ensure_ascii=False)
        guard = ModelStreamGuard()
        assembler = ToolCallAssembler()
        for character in encoded:
            delta = ToolCallDelta(arguments=character)
            guard.check(delta)
            assembler.add(delta.as_dict())
        self.assertEqual(assembler.finish()[0].arguments, expected)

    def test_new_content_resets_empty_run_and_structural_whitespace(self):
        guard = ModelStreamGuard()
        for char in '{"text": "ok"}':
            for _ in range(guard.MAX_EMPTY_DELTAS):
                guard.check(ToolCallDelta())
            guard.check(ToolCallDelta(arguments=char))
        guard = ModelStreamGuard()
        for char in '[1,2,3]':
            guard.check(ToolCallDelta(arguments=' ' * guard.MAX_JSON_WHITESPACE))
            guard.check(ToolCallDelta(arguments=char))

    def test_interleaved_calls_keep_string_escape_state_independent(self):
        guard = ModelStreamGuard()
        assembler = ToolCallAssembler()
        first = json.dumps({"text": '"\n\\' + ' ' * 2000})
        second = json.dumps({"text": "another"})
        for pos in range(max(len(first), len(second))):
            for index, encoded in enumerate([first, second]):
                if pos < len(encoded):
                    delta = ToolCallDelta(index=index, arguments=encoded[pos])
                    guard.check(delta)
                    assembler.add(delta.as_dict())
        self.assertEqual([call.arguments for call in assembler.finish()],
                         [json.loads(first), json.loads(second)])

    def test_malformed_marker_then_whitespace_loop_is_stopped(self):
        guard = ModelStreamGuard()
        guard.check(ToolCallDelta(arguments='{"command":"cat files","}\ue200genui\ue202{"'))
        with self.assertRaisesRegex(RuntimeError, 'whitespace outside JSON strings'):
            for _ in range(4000):
                guard.check(ToolCallDelta(arguments=' \n'))
        self.assertLess(guard.tool_deltas, 600)

    def test_rejection_closes_stream_and_fails_child_without_dispatch(self):
        cases = {
            'safety budget': ['x'] * 17,
            'empty argument deltas': [''] * 257,
            'whitespace outside JSON strings': [' ' * 1025],
        }
        for reason, arguments in cases.items():
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temp:
                registry = SessionRegistry(replace(load(), storage_dir=Path(temp), workspace=Path(temp), mcp={}))
                root = registry.create()
                child = registry.create(parent_session_id=root.session.id)
                emitted = 0
                closed = False

                def rejected_stream(*args, **kwargs):
                    nonlocal emitted, closed
                    try:
                        for argument in arguments:
                            emitted += 1
                            yield ModelChunk(tool_deltas=(ToolCallDelta(name='run_bash' if emitted == 1 else '',
                                                                       arguments=argument),))
                    finally:
                        closed = True

                try:
                    with patch.object(ModelStreamGuard, 'MAX_TOOL_DELTAS', 16 if reason == 'safety budget' else 65536), \
                         patch('agent.model.catalog.ModelCatalog.get_binding', return_value=(object(), object())), \
                         patch('agent.core.agent_runtime.stream', side_effect=rejected_stream):
                        child.start('exercise rejection without executing commands')
                        registry.wait()
                    self.assertTrue(closed)
                    records = child.session.events.read()
                    self.assertFalse(any(event['type'] in {'tool.requested', 'tool.completed'} for event in records))
                    self.assertEqual(sum(event['type'] == 'tool_call.delta' for event in records), emitted - 1)
                    self.assertIn(reason, next(event['reason'] for event in records if event['type'] == 'turn.failed'))
                    status = next(item for item in registry.monitor(root.session.id).watch()['changes']
                                  if item['id'] == f'agent:{child.session.id}')
                    self.assertEqual(status['status'], 'failed')
                    self.assertIn(reason, status['error'])
                finally:
                    for runtime in registry.items.values():
                        runtime.queue.put(None)
                        runtime.worker.join(5)
                    registry.store.database.close()

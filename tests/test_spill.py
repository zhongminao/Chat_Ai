import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.tools.executor import execute, read_file
from agent.tools.spill import spill_tool_output, _search_preview
from agent.tools.result import TextSection


class SpillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.text = 'first\npassword=example-secret\n' + '\n'.join(
            f'line-{n}-' + 'x' * 100 for n in range(3, 9)
        ) + '\nlast\n'

    def spill(self, **options):
        return spill_tool_output(self.text, **{
            'enabled': True, 'max_inline_lines': 2,
            'head_lines': 2, 'tail_lines': 2, 'max_line_chars': 30,
            'workspace': self.workspace, 'session_id': 'session', **options,
        })

    def test_saved_output_and_line_ranges(self):
        for directory in ['.spill', 'logs/output', str(self.workspace / 'absolute')]:
            with self.subTest(directory=directory):
                result = self.spill(directory=directory)
                path, = (self.workspace / directory / 'session').glob('*.log')
                relative = str(path.relative_to(self.workspace))
                self.assertIn(relative, result)
                self.assertIn('lines 1-2 of 9', result)
                self.assertIn('5 lines omitted', result)
                self.assertIn('lines 8-9 of 9', result)
                self.assertNotIn('example-secret', result)
                self.assertEqual(path.read_text(), self.text.replace('example-secret', '[redacted]'))
                self.assertIn('showing lines 3-4', read_file(self.workspace, relative, 3, 2))

    def test_single_long_line_is_bounded(self):
        result = self.spill(head_lines=1, tail_lines=0)
        self.assertNotIn('x' * 100, result)
        self.assertIn('8 lines omitted', result)
        result = self.spill(head_lines=0, tail_lines=2)
        self.assertIn('lines 8-9', result)
        self.assertIn('...[cut]...', result)

    def test_long_single_line_spills(self):
        result = spill_tool_output('a' * 500, enabled=True, max_inline_lines=100,
                                   head_lines=1, tail_lines=1, max_line_chars=30,
                                   workspace=self.workspace, session_id='session')
        self.assertIn('lines 1-1 of 1', result)
        self.assertNotIn('a' * 500, result)
        path, = (self.workspace / '.spill' / 'session').glob('*.log')
        self.assertEqual(path.read_text(), 'a' * 500)

    def test_small_or_disabled_output_does_not_create_spill_files(self):
        self.assertEqual(self.spill(enabled=False), self.text)
        self.assertEqual(self.spill(max_inline_lines=9, max_line_chars=200), self.text)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_invalid_directory_returns_bounded_output_without_writing(self):
        for directory in ['../outside', str(self.root / 'outside'), '', None, 123]:
            with self.subTest(directory=directory):
                result = self.spill(directory=directory)
                self.assertIn('[spill]', result)
                self.assertIn('保存失败', result)
                self.assertNotIn('example-secret', result)
                self.assertLess(len(result), len(self.text))
                self.assertEqual(list(self.workspace.iterdir()), [])
                self.assertFalse((self.root / 'outside').exists())

    def test_symlink_outside_workspace_is_rejected_before_writing(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.workspace / 'linked').symlink_to(outside, target_is_directory=True)
        self.assertIn('保存失败', self.spill(directory='linked'))
        self.assertEqual(list(outside.iterdir()), [])

    def test_write_failure_returns_bounded_output(self):
        with patch.object(Path, 'write_text', side_effect=OSError('disk full')):
            result = self.spill()
        self.assertIn('保存失败', result)
        self.assertNotIn('example-secret', result)

    def test_read_file_configuration_is_applied(self):
        (self.workspace / 'sample.txt').write_text('a' * 30 + '\nsecond\nthird', encoding='utf-8')
        result = execute(self.workspace, 'read_file', {'path': 'sample.txt'},
                         read_file_config={'limit': 1, 'max_line_chars': 20})
        self.assertIn('showing lines 1-1', result)
        self.assertEqual(len(result.splitlines()[1]), 20)
        self.assertIn('offset=2', result)

    def test_read_file_line_paging_and_long_line(self):
        path = self.workspace / 'sample.txt'
        path.write_text('one\n' + 'z' * 3500 + '\nthree\n', encoding='utf-8')
        first = read_file(self.workspace, 'sample.txt', limit=2)
        self.assertIn('3 lines total, showing lines 1-2', first)
        self.assertIn('offset=3', first)
        self.assertIn('...[cut]...', first)
        self.assertNotIn('z' * 3500, first)
        self.assertEqual(len(first.splitlines()[2]), 3000)
        self.assertEqual(len(read_file(self.workspace, 'sample.txt', offset=2, max_line_chars=3000).splitlines()[1]), 3000)
        self.assertEqual(len(read_file(self.workspace, 'sample.txt', offset=2, max_line_chars=100).splitlines()[1]), 100)
        self.assertIn('showing lines 3-3', read_file(self.workspace, 'sample.txt', offset=3))
        with self.assertRaises(ValueError):
            read_file(self.workspace, 'sample.txt', offset=4)
        with self.assertRaises(ValueError):
            read_file(self.workspace, 'sample.txt', offset=0)
        path.write_text('', encoding='utf-8')
        self.assertIn('0 lines', read_file(self.workspace, 'sample.txt'))

    def test_search_preview_details_only_first_ten_in_source_order(self):
        cards = [(f"[R{i}] title\nURL：https://example.com/{i}", f"excerpt-{i}", f"正文视图行：{i}–{i}")
                 for i in range(1, 51)]
        result = _search_preview("search", cards, 24000)
        self.assertIn("excerpt-10", result)
        self.assertNotIn("excerpt-11", result)
        self.assertIn(cards[-1][0], result)
        self.assertLess(result.index("[R10]"), result.index("[R11]"))
        self.assertLessEqual(len(result), 24000)

    def test_search_preview_falls_back_to_complete_compact_card(self):
        header = "[R1] " + "title" * 60 + "\nURL：https://example.com/" + "path" * 70
        cards = [(header, "excerpt" * 400, "正文视图行：1–10"),
                 ("[R2] " + "long" * 200, "excerpt-2", "正文视图行：11–20")]
        result = _search_preview("search", cards, 900)
        self.assertIn(header, result)
        self.assertIn("正文视图行：1–10", result)
        self.assertNotIn("excerpt", result)
        self.assertNotIn("[R2]", result)
        self.assertIn("完整索引", result)
        self.assertLessEqual(len(result), 900)

    def test_search_spill_retains_all_excerpts_in_index(self):
        sections = [TextSection(f"[R{i}] title\nURL：https://example.com/{i}",
                                f"excerpt-{i}", "body" * 100) for i in range(1, 13)]
        result = spill_tool_output(
            "raw" * 10000, enabled=True, max_inline_lines=2, head_lines=1,
            tail_lines=1, max_line_chars=3000, workspace=self.workspace,
            session_id="session", preview="search", sections=sections)
        self.assertNotIn("excerpt-11", result)
        path, = (self.workspace / ".spill/session").glob("*.index.txt")
        self.assertIn("excerpt-12", path.read_text())
        self.assertLessEqual(len(result), 24000)

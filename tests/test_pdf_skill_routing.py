"""PDF intents should surface relevant candidates without hiding the reader or unrelated skills.

Registration/routing only; never runs third-party PDF programs.
"""
import json
import tempfile
import unittest
from pathlib import Path

from agent.tools.search import search_resources


PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT / 'workspace'


class PdfRoutingTests(unittest.TestCase):
    def hits(self, query, top_k=5):
        return json.loads(search_resources(WORKSPACE, query, top_k=top_k))['results']

    def test_reading_stays_with_pdf_reader(self):
        for query in ('读取 PDF 并总结', '提取 PDF 文字', '扫描件 OCR 识别', '读取 report.pdf'):
            with self.subTest(query=query):
                self.assertEqual(self.hits(query)[0]['skill_id'], 'pdf_reader')

    def test_editing_and_generation_have_clear_candidates(self):
        cases = {
            '合并两个 PDF': 'anthropics-skills__pdf',
            '填写 PDF 表单': 'anthropics-skills__pdf',
            '生成 PDF 报告': 'anthropics-skills__pdf',
            'PDF 加水印': 'anthropics-skills__pdf',
            'PDF 转图片检查排版': 'openai-skills__pdf',
            'merge pdf': 'anthropics-skills__pdf',
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                result = self.hits(query)
                self.assertTrue(result)
                self.assertEqual(result[0]['skill_id'], expected)
                # The generic reader may still be offered as a secondary candidate;
                # selection remains with the LLM, not a hard single-skill route.
                self.assertTrue(any(reason.startswith(('intent:', 'alias:', 'capability:'))
                                    for reason in result[0]['match_reasons']))

    def test_existing_unrelated_routes_remain_available(self):
        for query, expected in {
            'Word 转 Markdown': 'convert_word_to_md',
            '写 README': 'github-awesome-copilot__create-readme',
            '代码审查': 'jeffallan-claude-skills__code-reviewer',
        }.items():
            with self.subTest(query=query):
                self.assertEqual(self.hits(query)[0]['skill_id'], expected)

    def test_only_weak_overlap_is_not_enough_to_return_a_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ws = root / 'workspace'
            ws.mkdir()
            skill = root / 'skills' / 'irrelevant'
            skill.mkdir(parents=True)
            (skill / 'manifest.yaml').write_text('name: irrelevant\ndescription: occasional report pdf\n', encoding='utf-8')
            (skill / 'SKILL.md').write_text('Unrelated notes', encoding='utf-8')
            self.assertEqual(json.loads(search_resources(ws, 'PDF'))['results'], [])

    def test_default_returns_multiple_real_matches_when_available(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ws = root / 'workspace'
            ws.mkdir()
            for name, intent in [('first', 'make chart'), ('second', 'chart')]:
                skill = root / 'skills' / name
                skill.mkdir(parents=True)
                (skill / 'manifest.yaml').write_text(
                    'name: ' + name + '\ntriggers:\n  intents: [' + intent + ']\n', encoding='utf-8')
                (skill / 'SKILL.md').write_text('Relevant', encoding='utf-8')
            result = json.loads(search_resources(ws, 'make chart'))['results']
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]['skill_id'], 'first')


if __name__ == '__main__':
    unittest.main()

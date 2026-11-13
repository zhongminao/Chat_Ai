"""Registration and intent-routing tests for the five Office/Word conversion skills.

Uses unittest assertions so pytest discovers it, while stdlib unittest also works when
pytest has not been installed in a minimal environment. No upstream scripts execute.
"""
import json
import unittest
from pathlib import Path

import yaml

from agent.tools.search import search_resources


PROJECT = Path(__file__).resolve().parents[1]
SKILLS = PROJECT / "skills"
WORKSPACE = PROJECT / "workspace"
SKILL_NAMES = (
    "office_docx", "office_xlsx", "office_pptx", "convert_word_to_md", "markdown_to_docx",
)


class OfficeSkillSearchTests(unittest.TestCase):
    def search(self, query):
        return json.loads(search_resources(WORKSPACE, query, top_k=10))["results"]

    def test_all_five_have_loadable_manifest_and_local_entrypoint_and_references(self):
        for name in SKILL_NAMES:
            with self.subTest(name=name):
                package = SKILLS / name
                raw = yaml.safe_load((package / "manifest.yaml").read_text(encoding="utf-8"))
                self.assertEqual(raw["name"], name)
                self.assertEqual(raw["entrypoint"], "SKILL.md")
                self.assertTrue(raw["allowed_tools"])
                self.assertTrue(set(raw["allowed_tools"]).issubset({"bash", "read_file", "read_image"}))
                self.assertTrue((package / raw["entrypoint"]).is_file())
                self.assertTrue((package / "LOCAL_NOTES.md").is_file())
                self.assertIn("LOCAL_NOTES.md", raw["references"])
                for ref in raw["references"]:
                    self.assertTrue((package / ref).is_file(), ref)
                result = next(row for row in self.search(name) if row["skill_id"] == name)
                self.assertEqual(result["instructions_path"], str((package / "SKILL.md").resolve()))
                self.assertEqual(set(result["references"]), {str((package / p).resolve()) for p in raw["references"]})
                self.assertIn("# ", result["usage"])
                # Search indexes only .py/.sh scripts; the Node .mjs entry is in package.
                if name != "markdown_to_docx":
                    self.assertTrue(result["scripts"])

    def test_general_docx_and_word_change_tracking_queries(self):
        for query in ("修订并添加 Word 批注到合同.docx", "edit Word tracked changes in agreement.docx"):
            with self.subTest(query=query):
                self.assertEqual(self.search(query)[0]["skill_id"], "office_docx")

    def test_excel_formula_and_workbook_queries(self):
        for query in ("编辑 Excel 公式，重新计算预算.xlsx", "create Excel workbook with formulas and format model.xlsx"):
            with self.subTest(query=query):
                self.assertEqual(self.search(query)[0]["skill_id"], "office_xlsx")

    def test_pptx_slide_and_template_queries(self):
        for query in ("编辑 PPT 幻灯片，把季度业绩写入 pitch.pptx", "create PowerPoint deck from board.potx"):
            with self.subTest(query=query):
                self.assertEqual(self.search(query)[0]["skill_id"], "office_pptx")

    def test_word_to_markdown_conversion_is_not_confused_with_word_authoring(self):
        for query in ("把 Word 转 Markdown 并提取 Word 内嵌图片", "convert DOCX folder to Markdown"):
            with self.subTest(query=query):
                self.assertEqual(self.search(query)[0]["skill_id"], "convert_word_to_md")

    def test_markdown_to_word_conversion_is_not_confused_with_word_extraction(self):
        for query in ("将 Markdown 导出为 Word", "convert Markdown to Word with embedded PNG images in DOCX"):
            with self.subTest(query=query):
                self.assertEqual(self.search(query)[0]["skill_id"], "markdown_to_docx")

    def test_pdf_reader_existing_registration_and_exclusions(self):
        self.assertEqual(self.search("读取 scan.pdf")[0]["skill_id"], "pdf_reader")
        self.assertNotIn("convert_word_to_md", [r["skill_id"] for r in self.search("Markdown 转 Word")])
        self.assertNotIn("markdown_to_docx", [r["skill_id"] for r in self.search("Word 转 Markdown")])
        self.assertNotIn("office_xlsx", [r["skill_id"] for r in self.search("Google Sheets API")])

    def test_preserved_upstream_assets_and_license(self):
        for name in ("office_docx", "office_xlsx", "office_pptx"):
            with self.subTest(name=name):
                self.assertIn("Apache License", (SKILLS / name / "LICENSE.txt").read_text(encoding="utf-8"))
                self.assertTrue((SKILLS / name / "UPSTREAM_THIRD_PARTY_NOTICES.md").is_file())
                self.assertTrue((SKILLS / name / "scripts/office/validate.py").is_file())
        for name in ("convert_word_to_md", "markdown_to_docx"):
            with self.subTest(name=name):
                self.assertIn("MIT License", (SKILLS / name / "UPSTREAM_LICENSE").read_text(encoding="utf-8"))
        self.assertTrue((SKILLS / "convert_word_to_md/scripts/convert_word_to_md.py").is_file())
        self.assertTrue((SKILLS / "markdown_to_docx/scripts/md-to-docx.mjs").is_file())


if __name__ == "__main__":
    unittest.main()

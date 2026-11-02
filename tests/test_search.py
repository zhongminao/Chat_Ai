import json
import tempfile
import unittest
from pathlib import Path

from agent.tools.search import search_resources


class SearchResourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.workspace = self.project / "workspace"
        self.workspace.mkdir()
        skill = self.project / "skills" / "pdf_reader"
        (skill / "scripts").mkdir(parents=True)
        (skill / "references").mkdir()
        (skill / "manifest.yaml").write_text(
            "name: pdf_reader\n"
            "version: 0.1.0\n"
            "description: Read PDF text\n"
            "triggers:\n"
            "  extensions: [.pdf]\n"
            "  intents: [pdf, extract pdf text]\n"
            "  aliases: [扫描件]\n"
            "  capabilities: [OCR]\n"
            "excludes: [PDF 编辑]\n"
            "references: [references/policy.md]\n",
            encoding="utf-8",
        )
        (skill / "SKILL.md").write_text("Use pdf_extract.sh, then read_file.", encoding="utf-8")
        (skill / "references/policy.md").write_text("OCR only for weak pages.", encoding="utf-8")
        (skill / "scripts/pdf_extract.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    def test_default_searches_skills_and_returns_usage(self):
        value = json.loads(search_resources(self.workspace, "读取 report.pdf"))
        self.assertEqual(value["resource_type"], "skill")
        self.assertEqual(value["results"][0]["skill_id"], "pdf_reader")
        self.assertIn("extension:.pdf", value["results"][0]["match_reasons"])
        self.assertIn("Use pdf_extract.sh", value["results"][0]["usage"])
        self.assertEqual(value["results"][0]["scripts"], [str((self.project / "skills/pdf_reader/scripts/pdf_extract.sh").resolve())])

    def test_alias_matches_and_excluded_intent_does_not(self):
        value = json.loads(search_resources(self.workspace, "读取扫描件中的文字"))
        self.assertEqual(value["results"][0]["skill_id"], "pdf_reader")
        self.assertIn("alias:扫描件", value["results"][0]["match_reasons"])
        excluded = json.loads(search_resources(self.workspace, "PDF 编辑"))
        self.assertEqual(excluded["results"], [])

    def test_knowledge_scope_is_reserved_without_affecting_skill_search(self):
        value = json.loads(search_resources(self.workspace, "产品知识", "knowledge"))
        self.assertEqual(value["results"], [])
        self.assertIn("not configured", value["message"])


if __name__ == "__main__":
    unittest.main()

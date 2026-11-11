import json
import tempfile
import shlex
import sys
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

    def test_commands_resolve_current_interpreter_and_relocated_skill_path(self):
        package = self.project / "skills/reader with spaces"
        (self.project / "skills/pdf_reader").rename(package)
        (package / "SKILL.md").write_text("{{python}} {{skill_dir}}/scripts/pdf_extract.sh", encoding="utf-8")
        value = json.loads(search_resources(self.workspace, "读取 report.pdf"))
        usage = value["results"][0]["usage"]
        self.assertEqual(shlex.split(usage), [sys.executable, str(package / "scripts/pdf_extract.sh")])
        self.assertNotIn("{{", usage)

    def test_alias_matches_and_excluded_intent_does_not(self):
        value = json.loads(search_resources(self.workspace, "读取扫描件中的文字"))
        self.assertEqual(value["results"][0]["skill_id"], "pdf_reader")
        self.assertIn("alias:扫描件", value["results"][0]["match_reasons"])
        self.assertFalse(any(reason in {"term:扫", "term:描", "term:件"}
                             for reason in value["results"][0]["match_reasons"]))
        excluded = json.loads(search_resources(self.workspace, "PDF 编辑"))
        self.assertEqual(excluded["results"], [])

    def test_search_json_is_multiline_and_parseable(self):
        text = search_resources(self.workspace, "report.pdf")
        self.assertGreater(len(text.splitlines()), 10)
        value = json.loads(text)
        self.assertEqual(value["results"][0]["skill_id"], "pdf_reader")
        self.assertNotIn("environment", value)
        self.assertNotIn("unavailable", value)

    def test_chinese_phrase_with_spaces_matches_explicit_trigger_not_weak_terms(self):
        skill = self.project / "skills" / "host"
        skill.mkdir()
        (skill / "manifest.yaml").write_text(
            "name: host\ntriggers:\n  intents: [部署环境]\n", encoding="utf-8")
        (skill / "SKILL.md").write_text("Host setup", encoding="utf-8")
        rows = json.loads(search_resources(self.workspace, "部署 环境 配置 系统信息"))["results"]
        self.assertEqual([row["skill_id"] for row in rows], ["host"])
        self.assertIn("intent:部署环境", rows[0]["match_reasons"])
        self.assertEqual(json.loads(search_resources(self.workspace, "部署 软件环境"))["results"], [])

    def test_knowledge_scope_is_reserved_without_affecting_skill_search(self):
        value = json.loads(search_resources(self.workspace, "产品知识", "knowledge"))
        self.assertEqual(value["results"], [])
        self.assertIn("not configured", value["message"])


if __name__ == "__main__":
    unittest.main()

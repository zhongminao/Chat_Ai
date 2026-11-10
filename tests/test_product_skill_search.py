"""Product-development skill routing, upstream integrity and licensing checks.

Uses only the standard-library unittest runner; the registered search module has
its existing PyYAML dependency. No upstream code is executed.
"""
import hashlib
import json
from pathlib import Path
import unittest

import yaml

from agent.tools.search import search_resources


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "workspace"
SKILLS = ROOT / "skills"
CATALOG = WORKSPACE / "skill_scout/staged/github-awesome-copilot/catalog.json"
STAGED = CATALOG.parent
CASES = {
    "github-awesome-copilot__prd": (
        "write a complete product requirements document for a software product",
        "编写软件产品需求文档",
    ),
    "github-awesome-copilot__create-specification": (
        "create an AI-ready technical specification for a solution",
        "编写适合 AI 理解的技术规格文档",
    ),
    "github-awesome-copilot__breakdown-feature-prd": (
        "write a feature PRD from a parent Epic",
        "根据父级 Epic 编写功能需求文档",
    ),
}


class ProductSkillSearchTests(unittest.TestCase):
    def test_search_has_correct_top_hit_in_english_and_chinese(self):
        for skill_id, queries in CASES.items():
            for query in queries:
                with self.subTest(skill_id=skill_id, query=query):
                    hits = json.loads(search_resources(WORKSPACE, query, top_k=10))["results"]
                    self.assertTrue(hits)
                    self.assertEqual(hits[0]["skill_id"], skill_id)
                    self.assertEqual(hits[0]["instructions_path"],
                                     str((SKILLS / skill_id / "SKILL.md").resolve()))
                    self.assertEqual(hits[0]["scripts"], [])
                    self.assertIn("# ", hits[0]["usage"])

    def test_registration_and_original_files_match_the_catalog_sha256(self):
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        self.assertEqual(catalog["repo"], "github/awesome-copilot")
        for skill_id in CASES:
            with self.subTest(skill_id=skill_id):
                item, = [entry for entry in catalog["items"]
                         if entry.get("package") == f"packages/{skill_id}"]
                self.assertEqual(item["status"], "installed_removed")
                self.assertEqual(Path(item["installed_path"]), SKILLS / skill_id)
                self.assertEqual(item["root_license"], "MIT")
                self.assertEqual(item["source_file_count"], 1)
                directory = SKILLS / skill_id
                manifest = yaml.safe_load((directory / "manifest.yaml").read_text(encoding="utf-8"))
                self.assertEqual(manifest["name"], skill_id)
                self.assertEqual(manifest["entrypoint"], "SKILL.md")
                self.assertTrue(set(manifest["allowed_tools"]).issubset({"read_file", "write_file"}))
                self.assertEqual(len(manifest["references"]), len(set(manifest["references"])))
                self.assertIn("UPSTREAM_LICENSE", manifest["references"])
                self.assertEqual(set(item["sha256"]), {"SKILL.md", "UPSTREAM_LICENSE"})
                for filename, expected in item["sha256"].items():
                    target = directory / filename
                    self.assertTrue(target.is_file())
                    self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), expected, filename)
                license_text = (directory / "UPSTREAM_LICENSE").read_text(encoding="utf-8")
                self.assertIn("MIT License", license_text)
                self.assertIn("Copyright GitHub, Inc.", license_text)
                self.assertEqual(item["sha256"]["UPSTREAM_LICENSE"],
                                 catalog["root_license_sha256"])
                self.assertEqual({p.relative_to(directory).as_posix() for p in directory.rglob("*")
                                  if p.is_file()},
                                 set(item["sha256"]) | {"manifest.yaml"} |
                                 ({"LOCAL_NOTES.md"} if (directory / "LOCAL_NOTES.md").is_file() else set()))
                for ref in manifest["references"]:
                    self.assertTrue((directory / ref).is_file(), ref)


if __name__ == "__main__":
    unittest.main()

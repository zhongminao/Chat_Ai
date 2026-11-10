"""Offline registration/routing and byte-integrity tests for three game skills.

Run with ``python3 -m unittest discover -s tests -p test_game_skill_search.py``.
Only reads files and calls the existing read-only search; never runs bundled scripts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import yaml

from agent.tools.search import search_resources


PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT / "workspace"
SKILLS = PROJECT / "skills"
CATALOG = (WORKSPACE / "skill_scout/staged/game-gamedev-skills/catalog.json")
PREFIX = "game-gamedev-skills__"
CASES = {
    "level-design": ("level whitebox layout and encounter pacing", "设计关卡白盒布局和关卡节奏"),
    "create-game-assets": ("pixel sprite asset pipeline and sprite asset provenance", "制作像素角色素材并核查美术素材版权溯源"),
    "prototype-fast": ("fast playable prototype with keep kill criteria", "快速可玩原型，做玩法原型验证"),
}


class GameSkillSearchTests(unittest.TestCase):
    def search(self, text):
        return json.loads(search_resources(WORKSPACE, text, top_k=10))["results"]

    def test_specific_english_and_chinese_intents_first_result(self):
        for slug, queries in CASES.items():
            for query in queries:
                with self.subTest(slug=slug, query=query):
                    result = self.search(query)
                    self.assertTrue(result)
                    self.assertEqual(result[0]["skill_id"], PREFIX + slug)
                    self.assertEqual(result[0]["instructions_path"],
                                     str((SKILLS / (PREFIX + slug) / "SKILL.md").resolve()))
                    self.assertTrue(result[0]["usage"].startswith("---\nname:"))
                    self.assertTrue(any(r.startswith(("intent:", "alias:", "capability:"))
                                        for r in result[0]["match_reasons"]))

    def test_generic_chinese_game_query_does_not_match_all_three(self):
        found = {r["skill_id"] for r in self.search("游戏")}
        self.assertFalse(found & {PREFIX + name for name in CASES})
        # The current token-overlap search indexes each package ID, all containing
        # "game"; English "game" alone can still match weakly, without any trigger.
        for row in self.search("game"):
            if row["skill_id"] in {PREFIX + name for name in CASES}:
                self.assertEqual(row["score"], 5)
                self.assertEqual(row["match_reasons"], ["term:game"])

    def test_catalog_sha256_original_byte_size_and_license(self):
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        self.assertEqual(catalog["root_license"], "Apache-2.0")
        self.assertEqual(catalog["fixed_commit"], "4cce500ce1a779b12fdd824be581c7d2ab4e7ba2")
        self.assertEqual(len(catalog["items"]), 3)
        self.assertEqual({item["skill"] for item in catalog["items"]}, set(CASES))
        license_digests = set()
        notice_digests = set()
        for item in catalog["items"]:
            with self.subTest(skill=item["skill"]):
                slug = item["skill"]
                package = SKILLS / (PREFIX + slug)
                self.assertEqual(item["status"], "installed_removed")
                self.assertEqual(Path(item["installed_path"]), package)
                self.assertEqual(item["license"], "Apache-2.0")
                self.assertEqual(item["commit"], catalog["fixed_commit"])
                self.assertEqual(item["package"], "packages/" + package.name)
                expected = item["files"]
                actual = {str(p.relative_to(package)) for p in package.rglob("*") if p.is_file()}
                self.assertEqual(actual - {"manifest.yaml", "LOCAL_NOTES.md"}, set(expected))
                self.assertEqual(set(expected) - actual, set())
                total = 0
                for rel, metadata in expected.items():
                    file_data = (package / rel).read_bytes()
                    self.assertEqual(hashlib.sha256(file_data).hexdigest(), metadata["sha256"], rel)
                    self.assertEqual(len(file_data), metadata["bytes"], rel)
                    total += len(file_data)
                self.assertEqual(total, item["bytes"])
                self.assertLessEqual(total, catalog["max_single_package_bytes"])
                license_digests.add(hashlib.sha256((package / "UPSTREAM_LICENSE").read_bytes()).hexdigest())
                notice_digests.add(hashlib.sha256((package / "UPSTREAM_NOTICE").read_bytes()).hexdigest())
                self.assertIn("Apache License", (package / "UPSTREAM_LICENSE").read_text(encoding="utf-8"))
                self.assertIn("Copyright", (package / "UPSTREAM_NOTICE").read_text(encoding="utf-8"))
                raw = yaml.safe_load((package / "manifest.yaml").read_text(encoding="utf-8"))
                self.assertEqual(raw["name"], package.name)
                self.assertEqual(raw["entrypoint"], "SKILL.md")
                self.assertEqual(raw["allowed_tools"], ["read_file"])
                self.assertEqual(raw["delivery"], "search_result")
                self.assertTrue({"LOCAL_NOTES.md", "UPSTREAM_LICENSE", "UPSTREAM_NOTICE"}
                                <= set(raw["references"]))
                for reference in raw["references"]:
                    self.assertTrue((package / reference).is_file(), reference)
        self.assertEqual(license_digests, {catalog["items"][0]["files"]["UPSTREAM_LICENSE"]["sha256"]})
        self.assertEqual(notice_digests, {catalog["items"][0]["files"]["UPSTREAM_NOTICE"]["sha256"]})

    def test_asset_scripts_preserved_but_not_executed(self):
        asset = SKILLS / (PREFIX + "create-game-assets")
        self.assertTrue((asset / "scripts/asset_report.py").is_file())
        self.assertTrue((asset / "scripts/build_preview_sheet.py").is_file())
        self.assertEqual((asset / "scripts/requirements.txt").read_text(encoding="utf-8"),
                         "Pillow>=10,<14\n")
        self.assertIn("先审查源码", (asset / "LOCAL_NOTES.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

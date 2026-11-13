"""Four staged video skills: read-only registration, provenance, and precise routing.

Only the stdlib unittest framework is used; upstream scripts never run.
"""
import hashlib
import json
from pathlib import Path
import unittest

from agent.tools.search import search_resources


PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT / "workspace"
SKILLS = PROJECT / "skills"
STAGED = WORKSPACE / "skill_scout/staged/video-zenstory-video-recap-skills"
CASES = {
    "script": (
        "write timestamped narration script from analyzed footage",
        "根据视频理解结果写带时间戳的解说词",
    ),
    "voiceover": (
        "synthesize recap narration from narration.json with TTS",
        "根据 narration.json 合成分段解说配音",
    ),
    "assemble": (
        "assemble recap video from tts_meta.json and source video",
        "将 tts_meta.json 旁白与源视频合成并烧录字幕",
    ),
    "recap": (
        "create complete Chinese narrated recap video from source footage",
        "从原始视频制作完整中文解说成片",
    ),
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VideoSkillSearchTests(unittest.TestCase):
    def search(self, query):
        return json.loads(search_resources(WORKSPACE, query, top_k=10))["results"]

    def test_each_specialist_is_first_hit_in_chinese_and_english(self):
        for suffix, queries in CASES.items():
            package_id = "video-recap-skills__video-" + suffix
            for query in queries:
                with self.subTest(skill=package_id, query=query):
                    results = self.search(query)
                    self.assertTrue(results)
                    self.assertEqual(results[0]["skill_id"], package_id)
                    self.assertEqual(results[0]["instructions_path"], str((SKILLS / package_id / "SKILL.md").resolve()))
                    self.assertTrue(any(reason.startswith("intent:") for reason in results[0]["match_reasons"]))

    def test_four_manifests_and_references_exist_with_read_only_tool_scope(self):
        for suffix in CASES:
            package_id = "video-recap-skills__video-" + suffix
            directory = SKILLS / package_id
            with self.subTest(skill=package_id):
                manifest = directory / "manifest.yaml"
                self.assertTrue(manifest.is_file())
                # Minimal stdlib parsing of manifest fields rather than PyYAML.
                text = manifest.read_text(encoding="utf-8")
                self.assertIn("name: " + package_id + "\n", text)
                self.assertIn("entrypoint: SKILL.md\n", text)
                self.assertIn("allowed_tools:\n- read_file\n", text)
                for shell_tool in ("bash", "run_bash"):
                    self.assertNotIn("- " + shell_tool + "\n", text)
                self.assertTrue((directory / "SKILL.md").is_file())
                refs = text.split("references:\n", 1)[1].splitlines()
                self.assertTrue(refs)
                self.assertTrue(all(line.startswith("- ") for line in refs))
                self.assertEqual(len(refs), len(set(refs)))
                for line in refs:
                    reference = line[2:]
                    self.assertTrue((directory / reference).is_file(), reference)
                for mandatory in ("LOCAL_NOTES.md", "UPSTREAM_CATALOG.json", "UPSTREAM_LICENSE"):
                    self.assertIn("- " + mandatory, refs)
                result = next(row for row in self.search(package_id) if row["skill_id"] == package_id)
                self.assertEqual({str((directory / line[2:]).resolve()) for line in refs}, set(result["references"]))
                self.assertIn("#", result["usage"])
                self.assertIn("不要自动", (directory / "LOCAL_NOTES.md").read_text(encoding="utf-8"))

    def test_catalog_sha256_file_bytes_original_license_and_staging_unchanged(self):
        catalog = json.loads((STAGED / "catalog.json").read_bytes())
        self.assertEqual(catalog["root_license"], "MIT")
        root_license = STAGED / catalog["root_license_copy"]
        self.assertEqual(sha256(root_license), catalog["root_license_sha256"])
        self.assertIn("Copyright (c) 2026 PiteChen", root_license.read_text(encoding="utf-8"))
        for suffix in CASES:
            package_id = "video-recap-skills__video-" + suffix
            item = next(entry for entry in catalog["items"] if entry["package"] == "packages/" + package_id)
            installed = SKILLS / package_id
            self.assertEqual(item["status"], "installed_removed")
            self.assertEqual(Path(item["installed_path"]), installed)
            with self.subTest(skill=package_id):
                self.assertEqual(item["license"], "MIT")
                self.assertEqual(item["source_commit"], catalog["source_commit"])
                self.assertEqual(item["file_count"], len(item["files"]))
                self.assertEqual(set(item["files"]), set(item["sha256"]))
                self.assertEqual(set(item["files"]), set(item["file_bytes"]))
                historical = json.loads((installed / "UPSTREAM_CATALOG.json").read_bytes())
                old = next(x for x in historical["items"] if x["package"] == item["package"])
                self.assertEqual(old["sha256"], item["sha256"])
                self.assertEqual((installed / "UPSTREAM_LICENSE").read_bytes(), root_license.read_bytes())
                for rel in item["files"]:
                    copy = installed / rel
                    self.assertTrue(copy.is_file(), f"installed file missing: {copy}")
                    self.assertEqual(sha256(copy), item["sha256"][rel], str(copy))
                    self.assertEqual(copy.stat().st_size, item["file_bytes"][rel], str(copy))


if __name__ == "__main__":
    unittest.main()

"""First-batch UI/web design Skills are installed and discoverable without runtime dependencies."""
import json
from pathlib import Path

import unittest
import yaml

from agent.tools.search import search_resources


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "workspace"
SKILLS = ROOT / "skills"
CASES = [
    ("wshobson-agents__accessibility-compliance", "WCAG 2.2 accessibility audit", "无障碍合规审查"),
    ("wshobson-agents__visual-design-foundations", "visual design foundations", "视觉设计基础"),
    ("wshobson-agents__responsive-design", "responsive web design", "响应式网页布局"),
    ("wshobson-agents__interaction-design", "interaction design", "交互设计"),
    ("anthropics-skills__frontend-design", "distinctive frontend design", "前端网页设计"),
]


class UIDesignSkillSearchTests(unittest.TestCase):
    def test_each_design_skill_searches_in_english_and_chinese_not_pdf(self):
        for skill_id, english, chinese in CASES:
            with self.subTest(skill_id=skill_id):
                check_design_skill_searches_in_english_and_chinese_not_pdf(skill_id, english, chinese)

    def test_design_skill_manifests_and_upstream_attributions_are_present(self):
        check_design_skill_manifests_and_upstream_attributions_are_present()

    def test_pdf_is_only_pdf_skill_and_does_not_route_to_ui_design(self):
        check_pdf_is_only_pdf_skill_and_does_not_route_to_ui_design()

def check_design_skill_searches_in_english_and_chinese_not_pdf(skill_id, english, chinese):
    for query in (english, chinese):
        result = json.loads(search_resources(WORKSPACE, query, top_k=10))["results"]
        assert result, query
        # A later registered WCAG audit specialist can outrank the general
        # accessibility guide; both remain available for the model to choose.
        assert any(item["skill_id"] == skill_id for item in result), query
        if query != "WCAG 2.2 accessibility audit":
            assert result[0]["skill_id"] == skill_id, query
        assert not any(item["skill_id"] == "pdf_reader" for item in result), query
        found = next(item for item in result if item["skill_id"] == skill_id)
        assert found["instructions_path"] == str((SKILLS / skill_id / "SKILL.md").resolve())
        assert found["usage"].strip().startswith("---\nname:")
        assert any(reason.startswith(("intent:", "alias:", "name:")) for reason in found["match_reasons"])


def check_design_skill_manifests_and_upstream_attributions_are_present():
    names = [yaml.safe_load(path.read_text(encoding="utf-8"))["name"]
             for path in SKILLS.glob("*/manifest.yaml")]
    assert len(names) == len(set(names)), "duplicate installed manifest names"
    assert len({entry[0] for entry in CASES}) == len(CASES)
    for skill_id, _, _ in CASES:
        directory = SKILLS / skill_id
        raw = yaml.safe_load((directory / "manifest.yaml").read_text(encoding="utf-8"))
        assert raw["name"] == directory.name
        assert raw["entrypoint"] == "SKILL.md"
        assert raw["allowed_tools"] == ["read_file"]
        assert raw["references"]
        assert len(raw["references"]) == len(set(raw["references"]))
        for reference in raw["references"]:
            assert (directory / reference).is_file(), reference
        assert "LOCAL_ADAPTATION.md" in raw["references"]
        if skill_id.startswith("wshobson-agents__"):
            assert "UPSTREAM_LICENSE" in raw["references"]
            assert "MIT License" in (directory / "UPSTREAM_LICENSE").read_text(encoding="utf-8")
        else:
            assert {"LICENSE.txt", "UPSTREAM_THIRD_PARTY_NOTICES.md"} <= set(raw["references"])


def check_pdf_is_only_pdf_skill_and_does_not_route_to_ui_design():
    results = json.loads(search_resources(WORKSPACE, "读取 report.pdf 提取 PDF 文字", top_k=10))["results"]
    assert results[0]["skill_id"] == "pdf_reader"
    assert not {entry[0] for entry in CASES} & {result["skill_id"] for result in results}

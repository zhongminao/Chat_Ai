import unittest

from agent.tools.extractive import extract_brief


class ExtractBriefTests(unittest.TestCase):
    def test_chinese_substrings_and_original_text(self):
        text = "这里介绍背景。深度学习改善图像识别。成本也需要考虑。"
        self.assertEqual(extract_brief(text, ["学习", "图像"]),
                         (["学习", "图像"], "深度学习改善图像识别。"))

    def test_english_case_and_acronym_boundaries(self):
        text = "The updated page mentions xpd and pd2. PD improves outcomes."
        self.assertEqual(extract_brief(text, ["pd"]), (["pd"], "PD improves outcomes."))
        self.assertEqual(extract_brief("The updated page.", ["pd"]),
                         ([], "The updated page."))
        self.assertEqual(extract_brief("评估PD患者的状态。", ["pd"]),
                         (["pd"], "评估PD患者的状态。"))

    def test_distinct_coverage_beats_repetition(self):
        text = "Alpha alpha alpha alpha. Alpha and beta are useful."
        self.assertEqual(extract_brief(text, ["alpha", "beta"]),
                         (["alpha", "beta"], "Alpha and beta are useful."))

    def test_adds_new_terms_and_restores_original_order(self):
        text = "Gamma matters. Unrelated background. Alpha and beta matter."
        self.assertEqual(extract_brief(text, ["alpha", "beta", "gamma"]),
                         (["alpha", "beta", "gamma"], "Gamma matters. Alpha and beta matter."))

    def test_selects_at_most_two_and_no_redundant_second(self):
        matched, brief = extract_brief("Alpha. Beta. Gamma.", ["alpha", "beta", "gamma"])
        self.assertEqual((matched, brief), (["alpha", "beta"], "Alpha. Beta."))
        self.assertEqual(extract_brief("Alpha is first. Alpha is second.", ["alpha"]),
                         (["alpha"], "Alpha is first."))

    def test_no_hit_falls_back_to_first_valid_sentence(self):
        self.assertEqual(extract_brief("# Heading\n首页\nFirst original sentence. Later one.", ["missing"]),
                         ([], "First original sentence."))
        self.assertEqual(extract_brief("原文内容。另一句话。", []), ([], "原文内容。"))

    def test_empty_and_noise_only(self):
        for text in ("", " \n\t", "# Heading\n[1] Smith, 2023.\nx = y + 2\nHome | About | Next\n---"):
            with self.subTest(text=text):
                self.assertEqual(extract_brief(text, ["Smith", "Heading"]), ([], ""))

    def test_noise_does_not_compete_with_prose(self):
        text = ("# Alpha beta gamma\n[1] Alpha beta gamma, 2022.\n"
                "1. Smith et al. Alpha beta gamma (2021).\nHome | Alpha | Beta\n"
                "[Alpha beta](https://example.com)\n"
                "alpha = beta + gamma\nf(x) = sin(x) + cos(x)\n"
                "$$\nalpha = beta + gamma\n$$\n"
                "```python\nalpha beta gamma\n```\n"
                "Alpha is useful.\n")
        self.assertEqual(extract_brief(text, ["alpha", "beta", "gamma"]),
                         (["alpha"], "Alpha is useful."))

    def test_prose_containing_equation_is_kept(self):
        text = "The method uses x = 1 for calibration."
        self.assertEqual(extract_brief(text, ["calibration"]), (["calibration"], text))

    def test_duplicate_sentences_and_terms(self):
        text = "Alpha is useful.\nAlpha is useful.\nALPHA is useful.\nBeta matters."
        self.assertEqual(extract_brief(text, ["Alpha", "alpha", "", "  ", "Beta", "Beta"]),
                         (["Alpha", "Beta"], "Alpha is useful. Beta matters."))

    def test_complete_sentences_punctuation_and_abbreviations(self):
        self.assertEqual(extract_brief("Dr. Smith uses PD. Next item.", ["PD"]),
                         (["PD"], "Dr. Smith uses PD."))
        self.assertEqual(extract_brief("Value is 3.14 for PD. Next item.", ["PD"]),
                         (["PD"], "Value is 3.14 for PD."))
        self.assertEqual(extract_brief("背景。‘学习很重要！’然后结束。", ["学习"]),
                         (["学习"], "‘学习很重要！’"))

    def test_long_sentence_clips_near_keyword(self):
        text = "A very long introductory passage " * 12 + "KEYWORD appears here " + "and more context " * 12 + "."
        matched, brief = extract_brief(text, ["keyword"], 60)
        self.assertEqual(matched, ["keyword"])
        self.assertIn("KEYWORD", brief)
        self.assertTrue(brief.startswith("…"))
        self.assertTrue(brief.endswith("…"))
        self.assertLessEqual(len(brief), 60)
        self.assertIn(brief.strip("…"), text)

    def test_complete_primary_is_not_cut_for_second(self):
        self.assertEqual(extract_brief("Alpha beta. Gamma matters.", ["alpha", "beta", "gamma"], 13),
                         (["alpha", "beta"], "Alpha beta."))

    def test_second_sentence_can_be_clipped_for_new_keyword(self):
        text = "Alpha beta. " + "Background words " * 20 + "gamma is relevant."
        matched, brief = extract_brief(text, ["alpha", "beta", "gamma"], 40)
        self.assertEqual(matched, ["alpha", "beta", "gamma"])
        self.assertTrue(brief.startswith("Alpha beta. …"))
        self.assertLessEqual(len(brief), 40)

    def test_length_budget_including_ellipses(self):
        for text, terms in (("这是比较长的中文学习句子。" * 8, ["学习"]),
                            ("prefix " * 20 + "keyword " + "suffix " * 20, ["keyword"]),
                            ("An original sentence without matches.", ["absent"])):
            for budget in range(-2, 100):
                with self.subTest(budget=budget, text=text[:20]):
                    matched, brief = extract_brief(text, terms, budget)
                    self.assertLessEqual(len(brief), max(0, budget))
                    if budget <= 0:
                        self.assertEqual((matched, brief), ([], ""))
                    elif "…" not in brief:
                        # Complete extracted sentences need no truncation marker.
                        self.assertIn(brief, text)

    def test_matched_terms_describe_visible_excerpt(self):
        matched, brief = extract_brief("Alpha " + "middle " * 100 + "beta.", ["alpha", "beta"], 20)
        for term in matched:
            self.assertIn(term, brief.lower())
        self.assertEqual(len(matched), 1)


if __name__ == "__main__":
    unittest.main()

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from agent.model.catalog import ModelCatalog
from agent.model.discovery import refresh_catalog


class ModelDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "providers.yaml"
        self.path.write_text("""# keep file header
providers:
  # live GPT provider
  gpt:
    base_url: http://gpt/v1
    api_key_default: key
    models:
      - id: gpt-6.1-sol
        name: GPT Sol
  deepseek:
    base_url: http://deepseek/v1
    api_key_default: key
    models: []
  # disabled local provider must remain untouched
  # local-unused:
  #   base_url: http://localhost:9/v1
  #   models: []
""")
        self.catalog = ModelCatalog(self.path, {"providers": {
            "gpt": {"models": {"gpt-6.1-sol": {"reasoning_efforts": ["low", "high"],
                                              "default_reasoning_effort": "high"}}}
        }})

    def test_refresh_runs_providers_concurrently_and_merges_manual_override(self):
        def response(url, key, timeout):
            time.sleep(0.06)
            if "gpt" in url:
                return {"data": [
                    {"id": "gpt-6.1-sol", "supported_endpoint_types": ["openai"]},
                    {"id": "gpt-image-2", "supported_endpoint_types": ["image-generation", "openai"]},
                ]}
            return {"data": [{"id": "deepseek-flash", "name": "Flash", "effort": {
                "supported_levels": ["low", "high", "max"], "default_level": "high"}}]}

        started = time.perf_counter()
        with patch("agent.model.discovery.get_json", side_effect=response):
            statuses = refresh_catalog(self.catalog)
        self.assertLess(time.perf_counter() - started, 0.11)
        self.assertEqual(statuses, {"gpt": "ok", "deepseek": "ok"})
        gpt = self.catalog.providers["gpt"]["models"][0]
        self.assertEqual(gpt["reasoning_efforts"], ["low", "high"])
        self.assertEqual(gpt["default_reasoning_effort"], "high")
        self.assertNotIn("gpt-image-2", [item["id"] for item in self.catalog.providers["gpt"]["models"]])
        deepseek = self.catalog.providers["deepseek"]["models"][0]
        self.assertEqual(deepseek["reasoning_efforts"], ["low", "high", "max"])
        self.assertEqual(deepseek["api_default_reasoning_effort"], "high")
        persisted = self.path.read_text()
        self.assertIn("# keep file header", persisted)
        self.assertIn("# live GPT provider", persisted)
        self.assertIn("# disabled local provider must remain untouched", persisted)
        self.assertIn("id: deepseek-flash", persisted)
        self.assertNotIn("deepseek-v4-pro", persisted)

    def test_failed_provider_keeps_previous_snapshot_while_others_refresh(self):
        self.catalog.replace_provider("gpt", {**self.catalog.providers["gpt"], "models": [{"id": "old"}]})
        def response(url, key, timeout):
            if "gpt" in url:
                raise OSError("offline")
            return {"data": [{"id": "deepseek-flash", "effort": {}}]}
        with patch("agent.model.discovery.get_json", side_effect=response):
            statuses = refresh_catalog(self.catalog)
        self.assertTrue(statuses["gpt"].startswith("error:"))
        self.assertEqual(self.catalog.providers["gpt"]["models"][0]["id"], "old")
        self.assertEqual(self.catalog.providers["deepseek"]["models"][0]["id"], "deepseek-flash")

    def test_refresh_preserves_commented_providers_attached_to_replaced_model_lists(self):
        from agent.model.catalog_file import write_models
        prefix = "providers:\n  gpt:\n    models:\n    - id: old  # model note\n"
        disabled = "  # local-disabled:\n  #   models:\n  #   - id: disabled-model\n"
        suffix = "  deepseek:\n    models: []\n"
        self.path.write_text(prefix + disabled + suffix)
        write_models(self.path, {"gpt": [{"id": "new"}]})
        text = self.path.read_text()
        self.assertIn(disabled, text)
        self.assertIn(suffix, text)
        self.assertIn("# model note", text)
        self.assertEqual(yaml.safe_load(text)["providers"]["gpt"]["models"], [{"id": "new"}])
        write_models(self.path, {"gpt": [{"id": "newer"}]})
        self.assertIn(disabled, self.path.read_text())

    def test_single_model_provider_refresh_checks_availability_without_writing_models(self):
        self.path.write_text("""# keep local comments
providers:
  local-one:
    base_url: http://local/v1
    default_model: fixed-model
    token_counter: llama_cpp
""")
        catalog = ModelCatalog(self.path)
        with patch("agent.model.discovery.get_json", return_value={"data": [{"id": "fixed-model"}]}):
            statuses = refresh_catalog(catalog)
        self.assertEqual(statuses, {"local-one": "ok"})
        self.assertNotIn("models", catalog.providers["local-one"])
        self.assertNotIn("models:", self.path.read_text())
        self.assertIn("# keep local comments", self.path.read_text())

    def test_catalog_forks_share_snapshot_but_not_http_bindings(self):
        child = self.catalog.fork()
        self.assertIs(child.providers, self.catalog.providers)
        self.assertIsNot(child, self.catalog)
        self.assertIsNone(child._binding)


if __name__ == "__main__":
    unittest.main()

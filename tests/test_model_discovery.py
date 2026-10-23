import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from agent.model.catalog import ModelCatalog
from agent.model.discovery import refresh_catalog
from agent.web import app as web


class ModelDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "providers.yaml"
        self.config = {"default_provider": "gpt", "providers": {
            "gpt": {"base_url": "http://gpt/v1", "api_key_default": "key",
                    "default_model": "sol", "defaults": {"default_reasoning_effort": "medium"},
                    "models": {"sol": {"default_reasoning_effort": "high"}}},
            "deepseek": {"base_url": "http://deepseek/v1", "default_model": "flash"}}}
        self.save()
        self.catalog = ModelCatalog(self.path)

    def save(self):
        self.path.write_text(yaml.safe_dump(self.config, sort_keys=False))

    def response(self, url, key, timeout):
        if "gpt" in url:
            return {"data": [{"id": "sol", "supported_endpoint_types": ["openai"]},
                             {"id": "image", "supported_endpoint_types": ["image-generation", "openai"]}]}
        return {"data": [{"id": "flash", "effort": {"default_level": "low"},
                          "input_modalities": ["text", "image"]}]}

    def test_discovery_merges_policy_without_writing_config_or_using_overrides_as_directory(self):
        before = self.path.read_bytes()
        self.assertEqual(self.catalog.models_for("gpt"), [])
        with patch("agent.model.discovery.get_json", side_effect=self.response):
            self.assertEqual(refresh_catalog(self.catalog), {"gpt": "ok", "deepseek": "ok"})
        self.assertEqual([m["id"] for m in self.catalog.models_for("gpt")], ["sol"])
        self.assertEqual(self.catalog.resolve("gpt").reasoning_effort, "high")
        self.assertEqual(self.catalog.resolve("deepseek").reasoning_effort, "low")
        self.assertTrue(self.catalog.supports_vision({"provider": "deepseek", "name": "flash"}))
        self.assertEqual(self.path.read_bytes(), before)

    def test_offline_empty_and_recovery_preserve_config_and_hide_empty_groups(self):
        before = self.path.read_bytes()
        with patch.object(web, "registry", SimpleNamespace(catalog=self.catalog)):
            with patch("agent.model.discovery.get_json", side_effect=self.response):
                self.assertEqual(len(web.models()["models"]), 2)
            with patch("agent.model.discovery.get_json", side_effect=OSError("offline")):
                self.assertEqual(web.models(), {"models": []})
            self.assertEqual(self.catalog.resolve("gpt").name, "sol")
            with patch("agent.model.discovery.get_json", return_value={"data": []}):
                self.assertEqual(web.models(), {"models": []})
            with patch("agent.model.discovery.get_json", side_effect=self.response):
                self.assertEqual(len(web.models()["models"]), 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_user_refresh_rereads_added_removed_providers_and_defaults_shared_with_forks(self):
        child = self.catalog.fork()
        self.config["providers"].pop("deepseek")
        self.config["providers"]["local-new"] = {
            "base_url": "http://new/v1", "default_model": "new",
            "defaults": {"vision": True, "thinking": "enabled"}}
        self.config["default_provider"] = "local-new"
        self.save()
        before = self.path.read_bytes()
        with patch.object(web, "registry", SimpleNamespace(catalog=self.catalog)), \
             patch("agent.model.discovery.get_json", return_value={"data": [{"id": "new", "supported_endpoint_types": ["openai"]}]}):
            groups = web.models()["models"]
        self.assertEqual([g["provider"] for g in groups], ["gpt", "local-new"])
        self.assertNotIn("deepseek", child.providers)
        self.assertEqual(child.default().thinking, "enabled")
        self.assertTrue(child.supports_vision(child.default().as_dict()))
        self.assertEqual(self.path.read_bytes(), before)

    def test_previous_snapshot_remains_visible_until_all_queries_finish(self):
        with patch("agent.model.discovery.get_json", side_effect=self.response):
            refresh_catalog(self.catalog)
        def response(url, key, timeout):
            self.assertEqual(self.catalog.models_for("gpt")[0]["id"], "sol")
            return {"data": []}
        with patch("agent.model.discovery.get_json", side_effect=response):
            refresh_catalog(self.catalog)
        self.assertEqual(self.catalog.models_for("gpt"), [])

    def test_api_metadata_provider_defaults_and_model_override_precedence(self):
        self.config["providers"]["deepseek"]["defaults"] = {
            "default_reasoning_effort": "high", "vision": False}
        self.config["providers"]["deepseek"]["models"] = {
            "flash": {"default_reasoning_effort": "max", "vision": True},
            "hidden": {"enabled": False}, "not-loaded": {"vision": True}}
        self.save()
        with patch("agent.model.discovery.get_json", return_value={"data": [
            {"id": "flash", "effort": {"default_level": "low"}}, {"id": "hidden"}]}):
            refresh_catalog(self.catalog)
        self.assertEqual([m["id"] for m in self.catalog.models_for("deepseek")], ["flash"])
        self.assertEqual(self.catalog.resolve("deepseek").reasoning_effort, "max")
        self.assertTrue(self.catalog.supports_vision({"provider": "deepseek", "name": "flash"}))

    def test_web_startup_queries_without_changing_provider_file(self):
        import asyncio
        before = self.path.read_bytes()
        async def startup():
            async with web.lifespan(web.app):
                await asyncio.sleep(0.05)
        with patch.object(web, "registry", SimpleNamespace(catalog=self.catalog)), \
             patch("agent.model.discovery.get_json", side_effect=self.response) as fetch:
            asyncio.run(startup())
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_queries_run_concurrently(self):
        from threading import Barrier
        barrier = Barrier(2, timeout=2)
        def response(url, key, timeout):
            barrier.wait()
            return {"data": []}
        with patch("agent.model.discovery.get_json", side_effect=response):
            self.assertEqual(refresh_catalog(self.catalog), {"gpt": "ok", "deepseek": "ok"})

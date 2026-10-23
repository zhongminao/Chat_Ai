import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agent.model.catalog import ModelCatalog, ModelTarget


class ModelBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'providers.yaml'
        self.path.write_text('''providers:
  test:
    base_url: https://example.invalid/v1
    api_key_default: test-key
    default_model: one
    models:
      - id: one
      - id: two
''')
        self.catalog = ModelCatalog(self.path)
        self.one = self.catalog.resolve('test', 'one')
        self.two = self.catalog.resolve('test', 'two')

    def tearDown(self):
        self.catalog.close()
        self.temp.cleanup()

    def test_gpt_defaults_to_medium_ignoring_stale_directory_policy(self):
        provider = self.catalog.providers.pop("test")
        provider["models"][0].update(reasoning_effort="high", default_reasoning_effort="high")
        self.catalog.providers["gpt"] = provider
        target = self.catalog.resolve("gpt", "one")
        self.assertEqual(target.reasoning_effort, "medium")
        self.assertEqual(target.as_dict()["reasoning_effort"], "medium")
        with patch("agent.model.catalog.ModelHttpClient"):
            _, adapter = self.catalog.get_binding(target)
            self.assertEqual(adapter.request_options(), {"reasoning_effort": "medium"})

    def test_gpt_explicit_config_overrides_medium_default(self):
        self.catalog.providers["gpt"] = self.catalog.providers.pop("test")
        self.catalog.overrides = {"providers": {"gpt": {"models": {
            "one": {"default_reasoning_effort": "high"},
            "two": {"default_reasoning_effort": "none"},
        }}}}
        self.assertEqual(self.catalog.resolve("gpt", "one").reasoning_effort, "high")
        self.assertEqual(self.catalog.resolve("gpt", "two").reasoning_effort, "none")
        self.assertEqual(self.one.reasoning_effort, "")  # Other providers unchanged.

    def test_local_provider_without_models_list_resolves_its_single_default(self):
        self.path.write_text("""providers:
  local-test:
    display_name: Local deployment service
    base_url: http://localhost/v1
    default_model: only-model
    token_counter: llama_cpp
""")
        catalog = ModelCatalog(self.path)
        target = catalog.resolve("local-test")
        self.assertEqual(target.name, "only-model")
        self.assertEqual(catalog.token_counter(target.as_dict()), "llama_cpp")
        self.assertEqual(catalog.models_for("local-test"), [{"id": "only-model", "name": "only-model"}])

    def test_reuses_only_current_binding_and_keeps_instances_independent(self):
        with patch('agent.model.catalog.ModelHttpClient') as clients, patch('agent.model.catalog.create_provider') as providers:
            first = self.catalog.get_binding(self.one)
            self.assertIs(self.catalog.get_binding(ModelTarget(**self.one.as_dict())), first)
            self.assertEqual(clients.call_count, 1)
            self.assertEqual(providers.call_count, 1)
            self.assertIsNot(self.catalog.get_binding(self.two), first)
            self.assertEqual(clients.call_count, 2)
            other = ModelCatalog(self.path)
            self.assertIsNot(other.get_binding(self.two), self.catalog.get_binding(self.two))
            self.assertEqual(clients.call_count, 3)
            self.assertIsNot(self.catalog.get_binding(self.one), first)
            self.assertEqual(clients.call_count, 4)

    def test_creation_failure_preserves_previous_binding_and_allows_retry(self):
        with patch('agent.model.catalog.ModelHttpClient', side_effect=[Mock(), RuntimeError('creation failed'), Mock()]) as clients, \
             patch('agent.model.catalog.create_provider', side_effect=[object(), object(), object()]):
            first = self.catalog.get_binding(self.one)
            with self.assertRaisesRegex(RuntimeError, 'creation failed'):
                self.catalog.get_binding(self.two)
            self.assertIs(self.catalog.get_binding(self.one), first)
            self.assertIsNot(self.catalog.get_binding(self.two), first)
            self.assertEqual(clients.call_count, 3)

    def test_deployment_can_override_base_url_without_copying_the_catalog(self):
        self.catalog.providers['test']['base_url_env'] = 'TEST_MODEL_BASE_URL'
        with patch.dict(os.environ, {'TEST_MODEL_BASE_URL': 'http://127.0.0.1:18100/test/v1'}), \
             patch('agent.model.catalog.ModelHttpClient') as clients, \
             patch('agent.model.catalog.create_provider'):
            self.catalog.get_binding(self.one)
            clients.assert_called_once_with(api_key='test-key', base_url='http://127.0.0.1:18100/test/v1')

    def test_empty_base_url_override_uses_configured_address(self):
        self.catalog.providers['test']['base_url_env'] = 'TEST_MODEL_BASE_URL'
        with patch.dict(os.environ, {'TEST_MODEL_BASE_URL': ''}), \
             patch('agent.model.catalog.ModelHttpClient') as clients, \
             patch('agent.model.catalog.create_provider'):
            self.catalog.get_binding(self.one)
            clients.assert_called_once_with(api_key='test-key', base_url='https://example.invalid/v1')

    def test_default_provider_override_does_not_change_the_model_directory(self):
        with patch.dict(os.environ, {'CHAT_AI_DEFAULT_PROVIDER': 'test'}):
            catalog = ModelCatalog(self.path)
        self.assertEqual(catalog.default(), self.one)
        self.assertEqual(catalog.providers, self.catalog.providers)

    def test_empty_default_provider_override_uses_catalog_default(self):
        with patch.dict(os.environ, {'CHAT_AI_DEFAULT_PROVIDER': ''}):
            catalog = ModelCatalog(self.path)
        self.assertEqual(catalog.default_provider, 'deepseek')


if __name__ == '__main__':
    unittest.main()

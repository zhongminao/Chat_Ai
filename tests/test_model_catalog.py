import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        self.temp.cleanup()

    def test_reuses_only_current_binding_and_keeps_instances_independent(self):
        with patch('openai.OpenAI') as clients, patch('agent.model.catalog.create_provider') as providers:
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
        with patch('openai.OpenAI', side_effect=[object(), RuntimeError('creation failed'), object()]) as clients, \
             patch('agent.model.catalog.create_provider', side_effect=[object(), object()]):
            first = self.catalog.get_binding(self.one)
            with self.assertRaisesRegex(RuntimeError, 'creation failed'):
                self.catalog.get_binding(self.two)
            self.assertIs(self.catalog.get_binding(self.one), first)
            self.assertIsNot(self.catalog.get_binding(self.two), first)
            self.assertEqual(clients.call_count, 3)


if __name__ == '__main__':
    unittest.main()

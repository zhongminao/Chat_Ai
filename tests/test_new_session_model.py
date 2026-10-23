"""New sessions choose once from discovery; historical and inherited models stay fixed."""
import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import yaml

from agent.core.session_registry import SessionRegistry
from agent.model.catalog import ModelCatalog
from agent.web.events import initialize
from agent.workflow.config import load


class NewSessionModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'providers.yaml'
        self.path.write_text(yaml.safe_dump({
            'default_provider': 'local-offline',
            'providers': {
                name: {'base_url': 'http://example.invalid/v1', 'default_model': model}
                for name, model in [('local-offline', 'old'), ('local-ready', 'local'),
                                    ('gpt', 'cloud-a'), ('deepseek', 'cloud-b')]
            },
        }))
        with patch.dict('os.environ', {'CHAT_AI_DEFAULT_PROVIDER': ''}):
            self.catalog = ModelCatalog(self.path)

    def tearDown(self):
        self.catalog.close()
        self.temp.cleanup()

    def discover(self, **providers):
        self.catalog._state['discovered'] = {
            name: [{'id': model} for model in models] for name, models in providers.items()
        }

    def test_available_default_wins_over_local_and_cloud_alternatives(self):
        self.discover(**{'local-offline': ['old'], 'local-ready': ['local'], 'gpt': ['cloud-a']})
        with patch('agent.model.catalog.random.choice') as choose:
            self.assertEqual(self.catalog.new_session_default().provider, 'local-offline')
        choose.assert_not_called()

    def test_offline_default_uses_available_local_before_cloud(self):
        self.discover(**{'local-ready': ['local'], 'gpt': ['cloud-a']})
        self.assertEqual(self.catalog.new_session_default().provider, 'local-ready')
        self.assertEqual(self.catalog.default_provider, 'local-offline')

    def test_cloud_only_fallback_randomly_selects_from_all_available_models(self):
        self.discover(gpt=['cloud-a', 'cloud-extra'], deepseek=['cloud-b'])
        with patch('agent.model.catalog.random.choice', return_value=('deepseek', 'cloud-b')) as choose:
            selected = self.catalog.new_session_default()
        self.assertEqual((selected.provider, selected.name), ('deepseek', 'cloud-b'))
        self.assertCountEqual(choose.call_args.args[0],
                              [('gpt', 'cloud-a'), ('gpt', 'cloud-extra'), ('deepseek', 'cloud-b')])

    def test_disabled_default_and_disabled_alternatives_are_not_selected(self):
        self.discover(**{'local-offline': ['old'], 'local-ready': ['local'], 'gpt': ['cloud-a']})
        self.catalog.providers['local-offline']['models'] = {'old': {'enabled': False}}
        self.catalog.providers['local-ready']['models'] = {'local': {'enabled': False}}
        self.assertEqual(self.catalog.new_session_default().provider, 'gpt')

    def test_default_model_must_be_discovered_not_just_another_model_in_same_provider(self):
        self.discover(**{'local-offline': ['different'], 'gpt': ['cloud-a']})
        self.assertEqual(self.catalog.new_session_default().name, 'different')

    def test_no_available_models_keeps_identity_without_inventing_availability(self):
        self.assertEqual(self.catalog.new_session_default(), self.catalog.default())
        self.assertTrue(all(not self.catalog.models_for(name) for name in self.catalog.providers))

    def test_missing_default_provider_can_fall_back(self):
        self.catalog._state['default_provider'] = 'removed'
        self.discover(**{'local-ready': ['local']})
        self.assertEqual(self.catalog.new_session_default().provider, 'local-ready')

    def test_environment_default_is_honored_when_available(self):
        with patch.dict('os.environ', {'CHAT_AI_DEFAULT_PROVIDER': 'gpt'}):
            catalog = ModelCatalog(self.path)
        catalog._state['discovered'] = {'gpt': [{'id': 'cloud-a'}], 'local-ready': [{'id': 'local'}]}
        self.assertEqual(catalog.new_session_default().provider, 'gpt')

    def test_web_initial_discovery_finishes_before_accepting_sessions(self):
        from agent.web import app as web

        async def startup():
            app = SimpleNamespace(state=SimpleNamespace())
            with patch.object(web, 'registry', SimpleNamespace(catalog=self.catalog)), \
                 patch.object(web, 'refresh_catalog') as refresh:
                async with web.lifespan(app):
                    refresh.assert_called_once_with(self.catalog, timeout=2)

        asyncio.run(startup())

    def test_choice_is_persisted_and_does_not_change_existing_or_child_sessions(self):
        registry = SessionRegistry(replace(load(), providers_file=self.path,
                                          workspace=self.root, storage_dir=self.root, mcp={}))
        registry.catalog = self.catalog
        self.discover(**{'local-ready': ['local']})
        runtimes = []
        try:
            first = registry.create()
            runtimes.append(first)
            selected = first.state['model']
            self.assertEqual(selected['provider'], 'local-ready')
            self.assertEqual(registry.store.metadata(first.session.id)['model'], selected)
            self.assertEqual(initialize(first, 0)[0]['model'], selected)
            self.discover(gpt=['cloud-a'])
            second = registry.create()
            runtimes.append(second)
            self.assertEqual(second.state['model']['provider'], 'gpt')
            self.assertEqual(first.state['model'], selected)
            child = registry.create(parent_session_id=first.session.id, model=selected)
            runtimes.append(child)
            self.assertEqual(child.state['model'], selected)
            explicit = registry.create(model=selected)
            runtimes.append(explicit)
            self.assertEqual(explicit.state['model'], selected)
            reopened = SessionRegistry(registry.config)
            try:
                restored = reopened.get(first.session.id)
                self.assertEqual(restored.state['model'], selected)
            finally:
                for runtime in reopened.items.values():
                    runtime.queue.put(None)
                    runtime.worker.join(5)
                reopened.store.database.close()
        finally:
            for runtime in runtimes:
                runtime.queue.put(None)
                runtime.worker.join(5)
            registry.store.database.close()
        self.assertEqual(yaml.safe_load(self.path.read_text())['default_provider'], 'local-offline')


if __name__ == '__main__':
    unittest.main()

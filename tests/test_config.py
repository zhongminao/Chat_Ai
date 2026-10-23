"""Project config resolves paths/prompts and loads model policy from providers only."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from agent.core.agent_factory import build_state
from agent.workflow.config import Config, load


class PromptConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'prompts').mkdir()
        self.main = self.root / 'prompts/main_agent.md'
        self.child = self.root / 'prompts/child_agent.md'
        self.main.write_text('主提示词 {workspace}，保留 JSON：{"ok": true}\n', encoding='utf-8')
        self.child.write_text('child {workspace}\n', encoding='utf-8')
        self.path = self.root / 'config.yaml'
        self.providers = self.root / 'providers.yaml'
        self.providers.write_text(yaml.safe_dump({
            'default_provider': 'gpt',
            'providers': {
                'gpt': {
                    'base_url': 'http://127.0.0.1:1/v1',
                    'default_model': 'gpt-test-high',
                    'defaults': {
                        'thinking': 'disabled',
                        'default_reasoning_effort': 'medium',
                    },
                    'models': {
                        'gpt-test-high': {'default_reasoning_effort': 'high'},
                    },
                },
            },
        }), encoding='utf-8')
        self.data = {
            'system_prompt_file': './prompts/main_agent.md',
            'child_system_prompt_file': './prompts/child_agent.md',
            'providers_file': './providers.yaml',
            'workspace': './workspace',
            'storage_dir': './session-data',
        }

    def config(self):
        self.path.write_text(yaml.safe_dump(self.data), encoding='utf-8')
        return load(self.path)

    def test_provider_policy_is_loaded_from_relative_providers_file(self):
        config = self.config()
        self.assertEqual(config.providers_file, self.providers)
        self.assertEqual(config.model, {
            'provider': 'gpt', 'name': 'gpt-test-high',
            'thinking': 'disabled', 'reasoning_effort': 'high',
        })
        self.assertNotIn('model_overrides', Config.__dataclass_fields__)
        self.assertEqual(build_state(config, {}, [])['model'], config.model)

    def test_config_constructs_catalog_with_only_the_providers_path(self):
        with patch('agent.workflow.config.ModelCatalog') as catalog:
            catalog.return_value.default.return_value.as_dict.return_value = {'provider': 'gpt'}
            self.config()
        catalog.assert_called_once_with(self.providers)

    def test_unlisted_default_model_inherits_provider_defaults(self):
        providers = yaml.safe_load(self.providers.read_text(encoding='utf-8'))
        providers['providers']['gpt']['default_model'] = 'gpt-test-medium'
        self.providers.write_text(yaml.safe_dump(providers), encoding='utf-8')
        self.assertEqual(self.config().model, {
            'provider': 'gpt', 'name': 'gpt-test-medium',
            'thinking': 'disabled', 'reasoning_effort': 'medium',
        })

    def test_environment_selects_config_when_no_path_is_given(self):
        self.config()
        with patch.dict(os.environ, {"CHAT_AI_CONFIG": str(self.path)}):
            self.assertEqual(load().storage_dir, self.root / "session-data")

    def test_explicit_path_takes_priority_over_environment(self):
        self.config()
        with patch.dict(os.environ, {"CHAT_AI_CONFIG": str(self.root / "missing.yaml")}):
            self.assertEqual(load(self.path).storage_dir, self.root / "session-data")

    def test_relative_utf8_files_are_loaded_and_factory_selects_by_role(self):
        config = self.config()
        self.assertEqual(config.storage_dir, self.root / "session-data")
        self.assertEqual(config.system_prompt, self.main.read_text(encoding='utf-8').strip())
        main = build_state(config, {}, [])
        child = build_state(config, {'parent_session_id': 'parent', 'system_prompt': 'legacy override'}, [])
        self.assertEqual(main['messages'][0]['content'],
                         '主提示词 '+str(config.workspace)+'，保留 JSON：{"ok": true}')
        self.assertEqual(child['messages'][0]['content'], 'child '+str(config.workspace))

    def test_reopening_history_uses_the_current_prompt_file(self):
        config = self.config()
        saved = [{'role': 'system', 'content': 'old prompt'}, {'role': 'user', 'content': 'saved context'}]
        events = [{'type': 'context.compacted', 'messages': saved}]
        self.main.write_text('updated {workspace}', encoding='utf-8')
        restored = build_state(self.config(), {}, events)
        self.assertEqual(restored['messages'], [
            {'role': 'system', 'content': 'updated '+str(config.workspace)}, *saved[1:]])

    def test_missing_blank_and_invalid_utf8_prompt_files_are_rejected(self):
        for value in [None, '', 'missing.md']:
            with self.subTest(path=value):
                self.data['system_prompt_file'] = value
                with self.assertRaisesRegex(ValueError, 'system_prompt_file'):
                    self.config()
        self.data['system_prompt_file'] = './prompts/main_agent.md'
        for content in [b' \n', b'\xff']:
            with self.subTest(content=content):
                self.main.write_bytes(content)
                with self.assertRaisesRegex(ValueError, 'system_prompt_file'):
                    self.config()

    def test_spill_directory_accepts_workspace_paths_without_creating_them(self):
        for directory in [".spill", "logs/output", str(self.root / "workspace/.spill")]:
            with self.subTest(directory=directory):
                self.data["spill"] = {"directory": directory}
                self.assertEqual(self.config().spill["directory"], directory)
                self.assertFalse((self.root / "workspace").exists())

    def test_spill_directory_rejects_invalid_and_outside_paths(self):
        outside = self.root / "outside"
        outside.mkdir()
        workspace = self.root / "workspace"
        workspace.mkdir()
        (workspace / "linked").symlink_to(outside, target_is_directory=True)
        for directory in ["../outside", str(outside), "linked", "", None, 123]:
            with self.subTest(directory=directory):
                self.data["spill"] = {"directory": directory}
                with self.assertRaisesRegex(ValueError, "spill.directory"):
                    self.config()
        self.assertEqual(list(outside.iterdir()), [])

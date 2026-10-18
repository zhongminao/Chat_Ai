"""Prompt files resolve from the config directory and retain role semantics."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from agent.core.agent_factory import build_state
from agent.workflow.config import PROJECT_ROOT, load


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
        self.data = {
            'system_prompt_file': './prompts/main_agent.md',
            'child_system_prompt_file': './prompts/child_agent.md',
            'providers_file': str(PROJECT_ROOT / 'agent/model/providers/providers.yaml'),
            'workspace': './workspace',
            'storage_dir': './session-data',
        }

    def config(self):
        self.path.write_text(yaml.safe_dump(self.data), encoding='utf-8')
        return load(self.path)

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

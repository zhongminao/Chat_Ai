"""Both agent roles receive the same workspace-deliverable linking policy."""
import unittest
from pathlib import Path

from agent.agentsessionstate.config import load
from agent.core.agent_factory import build_state


ROOT = Path(__file__).resolve().parents[1]


class DeliverablePromptPolicyTests(unittest.TestCase):
    def test_both_roles_require_existing_current_workspace_files_for_links(self):
        config = load(ROOT / 'config.yaml')
        for metadata in ({}, {'parent_session_id': 'parent'}):
            with self.subTest(role='child' if metadata else 'main'):
                prompt = build_state(config, metadata, [])['messages'][0]['content']
                self.assertIn(str(config.workspace.resolve()), prompt)
                if metadata:
                    for rule in ('resolved paths remain inside this workspace',
                                 'A directory is not a file link', 'outside paths are plain text',
                                 'only authorized, reviewed, shareable files',
                                 'do not link a dependent index.html alone'):
                        self.assertIn(rule, prompt)
                else:
                    for rule in ('解析后在当前工作区', '目录无浏览路由', '工作区外路径只作纯文本说明',
                                 '仅在授权且适合分享时', '不能只给 index.html'):
                        self.assertIn(rule, prompt)

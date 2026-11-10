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
                    self.assertIn('resolved path stays within the current', prompt)
                    self.assertIn('Directory paths are not browsable file URLs', prompt)
                    self.assertIn('Report paths outside this workspace as plain text', prompt)
                    self.assertIn('task authorizes the copy', prompt)
                else:
                    self.assertIn('解析后的路径仍在当前', prompt)
                    self.assertIn('目录本身没有文件浏览路由', prompt)
                    self.assertIn('工作区外路径只作为纯文本路径说明', prompt)
                    self.assertIn('任务授权复制', prompt)

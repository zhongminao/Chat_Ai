import tempfile
import unittest
from pathlib import Path

from agent.tools.approval import ApprovalGate
from agent.tools.executor import execute


class WriteAccessTests(unittest.TestCase):
    def test_authorization_is_per_call_and_only_absolute_external_write(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / 'workspace'
            workspace.mkdir()
            outside = base / 'outside.txt'
            gate = ApprovalGate('full_access', lambda *args, **kwargs: None)
            decision = gate.request('write_file', {'path': str(outside)}, None,
                                    session_id='main', run_id='run', call_id='call', is_mcp=False)
            self.assertEqual(decision, 'full_access')
            args = {'path': str(outside), 'content': 'written'}
            self.assertIn('outside workspace', execute(workspace, 'write_file', args))
            self.assertFalse(outside.exists())
            self.assertEqual(execute(workspace, 'write_file', args,
                                     allow_external_write=decision == 'full_access'), f'wrote {outside}')
            self.assertEqual(outside.read_text(), 'written')
            self.assertIn('outside workspace', execute(workspace, 'edit_file',
                {'path': str(outside), 'old': 'written', 'new': 'edited'},
                allow_external_write=True))
            self.assertIn('outside workspace', execute(workspace, 'write_file',
                {'path': '../relative.txt', 'content': 'blocked'}, allow_external_write=True))
            self.assertFalse((base / 'relative.txt').exists())
            self.assertIn('outside workspace', execute(workspace, 'write_file', args,
                allow_external_write=False))

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.tools.executor import read_file
from agent.tools.spill import spill_tool_output


class SpillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.text = "header\npassword=example-secret\n" + "长输出" * 100

    def spill(self, **options):
        return spill_tool_output(self.text, **{
            "enabled": True, "max_inline_chars": 100, "preview_chars": 7,
            "workspace": self.workspace, "session_id": "session", **options,
        })

    def test_saved_output_can_be_read_from_workspace(self):
        for directory in [".spill", "logs/output", str(self.workspace / "absolute")]:
            with self.subTest(directory=directory):
                result = self.spill(directory=directory)
                path, = (self.workspace / directory / "session").glob("*.log")
                self.assertIn(str(path.relative_to(self.workspace)), result)
                self.assertTrue(result.startswith(self.text[:7]))
                saved = read_file(self.workspace, str(path.relative_to(self.workspace)))
                self.assertEqual(saved, self.text.replace("example-secret", "[redacted]"))

    def test_small_or_disabled_output_does_not_create_spill_files(self):
        self.assertEqual(self.spill(enabled=False), self.text)
        self.assertEqual(self.spill(max_inline_chars=len(self.text)), self.text)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_invalid_directory_returns_bounded_output_without_writing(self):
        for directory in ["../outside", str(self.root / "outside"), "", None, 123]:
            with self.subTest(directory=directory):
                result = self.spill(directory=directory)
                self.assertTrue(result.startswith(self.text[:100]))
                self.assertIn("[spill]", result)
                self.assertIn("截断", result)
                self.assertLess(len(result), len(self.text))
                self.assertEqual(list(self.workspace.iterdir()), [])
                self.assertFalse((self.root / "outside").exists())

    def test_symlink_outside_workspace_is_rejected_before_writing(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.workspace / "linked").symlink_to(outside, target_is_directory=True)
        self.assertIn("截断", self.spill(directory="linked"))
        self.assertEqual(list(outside.iterdir()), [])

    def test_write_failure_returns_bounded_output(self):
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            result = self.spill()
        self.assertTrue(result.startswith(self.text[:100]))
        self.assertIn("截断", result)

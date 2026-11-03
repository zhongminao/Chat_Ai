"""Workflow smoke tests: only local simulated image/AX; never touches Windows pointer."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from workflow import run


class WorkflowTest(unittest.TestCase):
    def test_ax_one_shot_and_annotation(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            shot = root / "screen.png"
            preview = root / "marked.png"
            Image.new("RGB", (320, 180), "white").save(shot)
            result = run(shot, None, selector={"name": "Save", "role": "button"},
                         nodes=[{"name": "Save", "role": "button", "bbox": {
                             "x": 100, "y": 60, "width": 60, "height": 30}}], output=preview)
            self.assertEqual((result["x"], result["y"]), (130, 75))
            self.assertEqual(result["source"], "ax_exact_unique")
            self.assertTrue(preview.is_file())
            with Image.open(preview) as marked:
                self.assertEqual(marked.size, (320, 180))


if __name__ == "__main__":
    unittest.main()

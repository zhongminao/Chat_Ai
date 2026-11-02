"""Smoke tests for the fixed PDF script workflow (requires Poppler)."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "pdf_reader" / "scripts"
SAMPLE = Path(__file__).resolve().parents[1] / "3805712.3808466.pdf"


@unittest.skipUnless(SAMPLE.is_file() and all(shutil.which(cmd) for cmd in ("pdfinfo", "pdftotext")),
                     "PDF fixture or Poppler unavailable")
class PdfReaderScriptsTests(unittest.TestCase):
    def test_detect_multicolumn_and_extract_modes(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            subprocess.run([SCRIPTS / "pdf_read.sh", SAMPLE, directory], check=True, capture_output=True)
            probe = (directory / "probe.txt").read_text()
            self.assertIn("pages=6", probe)
            self.assertIn("layout_mode=multi", probe)
            self.assertIn("column_count=2", probe)
            self.assertIn("recommended_mode=raw", probe)
            self.assertIn("mode=raw", (directory / "read.meta").read_text())
            self.assertIn("SkillForge", (directory / "text.txt").read_text())
            for mode in ("layout", "raw", "tsv"):
                target = directory / f"{mode}.txt"
                subprocess.run([SCRIPTS / "pdf_extract.sh", SAMPLE, target, mode], check=True,
                               capture_output=True)
                self.assertGreater(target.stat().st_size, 1000)
            self.assertIn("###PAGE###", (directory / "tsv.txt").read_text())

    def test_invalid_mode_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "no.txt"
            result = subprocess.run([SCRIPTS / "pdf_extract.sh", SAMPLE, target, "bad-mode"],
                                    capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(target.exists())

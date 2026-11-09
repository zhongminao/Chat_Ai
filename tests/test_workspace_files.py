"""Read-only workspace paths are HTTP URLs, not arbitrary filesystem access."""
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.web.workspace_files import workspace_file_router


class WorkspaceFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.app = FastAPI()
        self.app.get("/api/ping")(lambda: {"ok": True})
        self.app.include_router(workspace_file_router(self.workspace))
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def url(self, name=""):
        return quote(str(self.workspace / name), safe="/")

    def test_markdown_opens_as_utf8_plain_text_and_supports_head(self):
        name = "交接 #1?.md"
        text = "# 交接文档\n\n**原始 Markdown**\n"
        (self.workspace / name).write_text(text, encoding="utf-8")
        response = self.client.get(self.url(name))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, text)
        self.assertEqual(response.headers["content-type"], "text/plain; charset=utf-8")
        self.assertTrue(response.headers["content-disposition"].startswith("inline;"))
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        response = self.client.head(self.url(name))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertEqual(int(response.headers["content-length"]), len(text.encode()))

    def test_media_types_and_downloads(self):
        for name, data, mime, disposition in [
            ("photo.png", b"png", "image/png", "inline"),
            ("report.pdf", b"%PDF", "application/pdf", "inline"),
            ("notes.txt", b"notes", "text/plain", "inline"),
            ("page.html", b"<script>alert(1)</script>", "text/html", "attachment"),
            ("image.svg", b"<svg/>", "image/svg+xml", "attachment"),
            ("binary.unknown", b"\x00\xff", "application/octet-stream", "attachment"),
        ]:
            with self.subTest(name=name):
                (self.workspace / name).write_bytes(data)
                response = self.client.get(self.url(name))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, data)
                self.assertTrue(response.headers["content-type"].startswith(mime))
                self.assertTrue(response.headers["content-disposition"].startswith(disposition + ";"))

    def test_no_directory_listing_missing_files_or_outside_access(self):
        (self.workspace / "folder").mkdir()
        outside = self.base / "secret.md"
        outside.write_text("secret", encoding="utf-8")
        (self.workspace / "escape.md").symlink_to(outside)
        (self.workspace / "outside").symlink_to(self.base, target_is_directory=True)
        for url in [self.url(), self.url("folder"), self.url("missing.md"),
                    str(outside), self.url("escape.md"), self.url("outside/secret.md"),
                    self.url() + "/%2e%2e/secret.md", self.url() + "/%2F" + str(outside).lstrip("/"),
                    self.url() + "/bad%00.md"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn("secret", response.text)

    def test_inside_symlinks_remain_accessible_and_routes_are_read_only(self):
        (self.workspace / "notes.md").write_text("notes", encoding="utf-8")
        (self.workspace / "alias.md").symlink_to(self.workspace / "notes.md")
        self.assertEqual(self.client.get(self.url("alias.md")).text, "notes")
        self.assertEqual(self.client.get("/api/ping").json(), {"ok": True})
        for method in ["POST", "PUT", "DELETE"]:
            self.assertEqual(self.client.request(method, self.url("notes.md")).status_code, 405)

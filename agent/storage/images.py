"""Session images and names shared by CLI, Web and model requests."""
from __future__ import annotations

import base64
import hashlib
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .database import Database


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
FORMATS = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"), "WEBP": ("image/webp", "webp")}


class ImageStore:
    def __init__(self, database: Database, session_id: str, session_directory: Path):
        self.database = database
        self.session_id = session_id
        self.root = session_directory / "attachments"

    def list(self) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute('SELECT * FROM images WHERE session_id=? ORDER BY ordinal', (self.session_id,)).fetchall()
        return [{key: row[key] for key in row.keys() if key != 'session_id'} for row in rows]

    def get(self, selector: str) -> dict:
        path = Path(selector).expanduser()
        for image in self.list():
            if selector == image["id"] or (path.is_absolute() and path.resolve() == self._path(image).resolve()):
                return image
        raise FileNotFoundError("图片不存在")

    def add(self, data: bytes, filename: str = "image") -> dict:
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise ValueError("图片不能为空，单张图片不能超过 10 MB")
        try:
            with Image.open(BytesIO(data)) as image:
                if image.format not in FORMATS or getattr(image, "is_animated", False):
                    raise ValueError("只支持静态 PNG、JPEG 和 WebP 图片")
                width, height = image.size
                if width * height > MAX_IMAGE_PIXELS:
                    raise ValueError("图片不能超过 2000 万像素")
                mime, extension = FORMATS[image.format]
                image.load()
                ImageOps.exif_transpose(image, in_place=True)
                image.thumbnail((480, 480))
                preview = BytesIO()
                image.convert("RGBA").save(preview, format="PNG")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("无法读取图片文件") from exc
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1][:200] or "image"
        label = filename[:80]
        identifier = uuid.uuid4().hex
        digest = hashlib.sha256(data).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{identifier}.{extension}"
        thumbnail = self.root / f"{identifier}.preview.png"
        try:
            path.write_bytes(data)
            thumbnail.write_bytes(preview.getvalue())
            with self.database.connect(write=True) as connection:
                row = connection.execute('SELECT image_seq FROM sessions WHERE id=?', (self.session_id,)).fetchone()
                if row is None:
                    raise FileNotFoundError(self.session_id)
                ordinal = row['image_seq'] + 1
                connection.execute('UPDATE sessions SET image_seq=? WHERE id=?', (ordinal, self.session_id))
                connection.execute('INSERT INTO images VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                   (identifier, self.session_id, ordinal, label, filename, mime, width, height, len(data), extension, digest))
        except BaseException:
            path.unlink(missing_ok=True)
            thumbnail.unlink(missing_ok=True)
            raise
        return {"id": identifier, "name": label, "ordinal": ordinal, "mime": mime, "filename": filename,
                "width": width, "height": height, "size": len(data), "extension": extension, "sha256": digest}

    def add_file(self, path: Path) -> dict:
        if image := self.find_file(path):
            return image
        with path.expanduser().open("rb") as file:
            return self.add(file.read(MAX_IMAGE_BYTES + 1), path.name)

    def find_file(self, path: Path) -> dict | None:
        """Reuse a saved path or an identical snapshot; changed bytes get a new ID."""
        path = path.expanduser().resolve()
        assets = self.list()
        for image in assets:
            if path == self._path(image).resolve():
                if not path.is_file():
                    raise FileNotFoundError("会话图片文件不存在")
                return image
        with path.open("rb") as file:
            data = file.read(MAX_IMAGE_BYTES + 1)
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise ValueError("图片不能为空，单张图片不能超过 10 MB")
        digest = hashlib.sha256(data).hexdigest()
        for image in assets:
            saved = self._path(image)
            if saved.is_file() and digest == image['sha256']:
                return image
        return None

    def path(self, selector: str, preview: bool = False) -> Path:
        return self._path(self.get(selector), preview)

    def _path(self, image: dict, preview: bool = False) -> Path:
        extension = "preview.png" if preview else image["extension"]
        return self.root / f"{image['id']}.{extension}"

    def url(self, image: dict) -> str:
        return f"/api/sessions/{self.session_id}/images/{image['id']}/content"

    def markdown(self, image: dict) -> str:
        label = image["name"].replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        return f"![{label}]({self.url(image)})"

    def describe(self, image: dict) -> str:
        return f"图片编号 {image['ordinal']}\n路径：{self._path(image).resolve()}"

    def data_url(self, selector: str) -> str:
        image = self.get(selector)
        data = self.path(image["id"]).read_bytes()
        return f"data:{image['mime']};base64,{base64.b64encode(data).decode('ascii')}"

"""Session images and names shared by CLI, Web and model requests."""
from __future__ import annotations

import base64
import hashlib
import json
import uuid
from io import BytesIO
from pathlib import Path

from filelock import FileLock
from PIL import Image, ImageOps, UnidentifiedImageError


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
FORMATS = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"), "WEBP": ("image/webp", "webp")}
LEGACY_ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
            "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth")


def image_number(ordinal: int) -> str:
    return f"{ordinal:02d}"


class ImageStore:
    def __init__(self, session_directory: Path):
        self.root = session_directory / "attachments"
        self.index = self.root / "index.json"
        self.lock = FileLock(str(session_directory / ".images.lock"))

    def _read(self) -> dict:
        if not self.index.exists():
            return {"version": 2, "next": 1, "images": []}
        data = json.loads(self.index.read_text(encoding="utf-8"))
        if data.get("version", 1) < 2:
            for image in data["images"]:
                ordinal = image["ordinal"]
                old_name = LEGACY_ORDINALS[ordinal - 1] if ordinal <= len(LEGACY_ORDINALS) else f"image-{ordinal}"
                if image["name"] == old_name:
                    image["name"] = image["filename"][:80]
            data["version"] = 2
        return data

    def _write(self, data: dict) -> None:
        temporary = self.index.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.index)

    def list(self) -> list[dict]:
        return self._read()["images"]

    def get(self, selector: str) -> dict:
        path = Path(selector).expanduser()
        for image in self.list():
            if selector == image["id"] or (path.is_absolute() and path.resolve() == self._path(image).resolve()):
                return image
        raise FileNotFoundError("图片不存在")

    @staticmethod
    def _name(name: str) -> str:
        name = name.strip()
        if not name or len(name) > 80 or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ValueError("图片名称需要 1–80 个字符，不能包含换行")
        return name

    def add(self, data: bytes, filename: str = "image", name: str | None = None) -> dict:
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
        with self.lock:
            index = self._read()
            ordinal = index["next"]
            filename = filename.replace("\\", "/").rsplit("/", 1)[-1][:200] or "image"
            label = self._name(filename[:80] if name is None else name)
            identifier = uuid.uuid4().hex
            asset = {"id": identifier, "name": label, "ordinal": ordinal, "mime": mime,
                     "filename": filename,
                     "width": width, "height": height, "size": len(data), "extension": extension,
                     "sha256": hashlib.sha256(data).hexdigest()}
            self.root.mkdir(parents=True, exist_ok=True)
            path = self.root / f"{identifier}.{extension}"
            path.write_bytes(data)
            thumbnail = self.root / f"{identifier}.preview.png"
            thumbnail.write_bytes(preview.getvalue())
            index["images"].append(asset)
            index["next"] = ordinal + 1
            try:
                self._write(index)
            except Exception:
                path.unlink(missing_ok=True)
                thumbnail.unlink(missing_ok=True)
                raise
            return asset

    def add_file(self, path: Path, name: str | None = None) -> dict:
        if image := self.find_file(path):
            return self.rename(image["id"], name) if name is not None else image
        with path.expanduser().open("rb") as file:
            return self.add(file.read(MAX_IMAGE_BYTES + 1), path.name, name)

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
            if saved.is_file() and digest == (image.get("sha256") or hashlib.sha256(saved.read_bytes()).hexdigest()):
                return image
        return None

    def rename(self, selector: str, name: str) -> dict:
        with self.lock:
            image = self.get(selector)
            index = self._read()
            label = self._name(name)
            updated = {**image, "name": label}
            index["images"] = [updated if entry["id"] == image["id"] else entry for entry in index["images"]]
            self._write(index)
            return updated

    def path(self, selector: str, preview: bool = False) -> Path:
        return self._path(self.get(selector), preview)

    def _path(self, image: dict, preview: bool = False) -> Path:
        extension = "preview.png" if preview else image["extension"]
        return self.root / f"{image['id']}.{extension}"

    def describe(self, image: dict) -> str:
        return (f"编号：{image_number(image['ordinal'])}\n名称：{image['name']}\n"
                f"路径：{self._path(image).resolve()}")

    def data_url(self, selector: str) -> str:
        image = self.get(selector)
        data = self.path(image["id"]).read_bytes()
        return f"data:{image['mime']};base64,{base64.b64encode(data).decode('ascii')}"

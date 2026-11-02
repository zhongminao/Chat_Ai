"""Session-owned opaque file uploads; no parsing or database migration."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import BinaryIO

MAX_FILE_BYTES = 25 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024
_ID = re.compile(r"[0-9a-f]{32}\Z")
_EXTENSION = re.compile(r"[a-z0-9]{1,12}\Z")


def safe_filename(value: str) -> str:
    basename = (value or "").replace("\\", "/").rsplit("/", 1)[-1]
    basename = "".join("_" if ord(c) < 32 or ord(c) == 127 or c in "\u2028\u2029" else c
                       for c in basename).strip(" .")
    return basename[:200].strip(" .") or "file"


class FileTooLarge(ValueError):
    pass


class FileStore:
    def __init__(self, session_directory: Path):
        self.root = session_directory / "attachments"

    def _check_root(self) -> None:
        # Never follow a replaced attachments directory into an outside location.
        if self.root.is_symlink() or self.root.resolve() != self.root.parent.resolve() / "attachments":
            raise ValueError("无效的附件目录")

    def add(self, source: BinaryIO, filename: str) -> dict:
        name = safe_filename(filename)
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if not _EXTENSION.fullmatch(extension):
            extension = "bin"
        identifier = uuid.uuid4().hex
        self._check_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self._check_root()
        path = self.root / f"{identifier}.{extension}"
        metadata = self.root / f"{identifier}.file.json"
        size = 0
        try:
            with path.open("xb") as output:
                while chunk := source.read(_CHUNK_BYTES):
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise FileTooLarge("文件不能超过 25 MB")
                    output.write(chunk)
            if not size:
                raise ValueError("文件不能为空")
            record = {"id": identifier, "name": name, "filename": name,
                      "size": size, "extension": extension}
            with metadata.open("x", encoding="utf-8") as output:
                json.dump(record, output, ensure_ascii=False)
            return {**record, "path": str(path.resolve())}
        except BaseException:
            path.unlink(missing_ok=True)
            metadata.unlink(missing_ok=True)
            raise

    def get(self, identifier: str) -> dict:
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
            raise FileNotFoundError("附件不存在")
        try:
            self._check_root()
            metadata = self.root / f"{identifier}.file.json"
            if metadata.is_symlink():
                raise FileNotFoundError("附件不存在")
            record = json.loads(metadata.read_text(encoding="utf-8"))
            extension = record["extension"]
            if record["id"] != identifier or not _EXTENSION.fullmatch(extension):
                raise ValueError("无效的附件元数据")
            path = self.root / f"{identifier}.{extension}"
            if not path.is_file() or path.is_symlink() or path.stat().st_size != record["size"]:
                raise FileNotFoundError("附件不存在")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise FileNotFoundError("附件不存在") from exc
        return {**record, "path": str(path.resolve())}

    def format_message(self, text: str, identifiers: list[str]) -> str:
        if not identifiers:
            return text
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("附件引用不能重复")
        files = [self.get(identifier) for identifier in identifiers]
        return "\n".join(f"附件：{file['filename']}，路径：{file['path']}" for file in files) + (f"\n\n{text}" if text else "")

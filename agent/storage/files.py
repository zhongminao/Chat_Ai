"""Session-owned opaque file and directory uploads; no database migration."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import uuid
from pathlib import Path
from typing import BinaryIO

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FOLDER_BYTES = 100 * 1024 * 1024
MAX_FOLDER_FILES = 1000
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


def _directory_name(value: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 200
            or value in (".", "..") or value != value.strip(" .")
            or any(c in value for c in "/\\:")
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("无效的文件夹名称")
    return value


def _relative_path(value: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 1024
            or "\\" in value or value.startswith("/") or "\x00" in value):
        raise ValueError("无效的相对路径")
    parts = value.split("/")
    if any(not p or p in (".", "..") or len(p) > 255 or p != p.strip(" .")
           or ":" in p or any(ord(c) < 32 or ord(c) == 127 for c in p) for p in parts):
        raise ValueError("无效的相对路径")
    return value


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

    def add_folder(self, sources: list[BinaryIO], paths: list[str], name: str) -> dict:
        """Create one attachment from parallel streams and POSIX paths relative to its root."""
        name = _directory_name(name)
        if not sources or len(sources) != len(paths):
            raise ValueError("文件与相对路径数量不匹配或文件夹为空")
        if len(sources) > MAX_FOLDER_FILES:
            raise ValueError(f"文件夹不能超过 {MAX_FOLDER_FILES} 个文件")
        paths = [_relative_path(path) for path in paths]
        folded = [path.casefold() for path in paths]
        if len(set(folded)) != len(folded):
            raise ValueError("文件夹内存在重复文件路径")
        file_paths = set(folded)
        for path in folded:
            parts = path.split("/")
            if any("/".join(parts[:index]) in file_paths for index in range(1, len(parts))):
                raise ValueError("文件路径与目录冲突")

        identifier = uuid.uuid4().hex
        self._check_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self._check_root()
        folder = self.root / f"{identifier}.folder"
        metadata = self.root / f"{identifier}.folder.json"
        folder.mkdir()  # exclusive; a UUID collision must not delete someone else's attachment
        sizes = []
        total = 0
        metadata_created = False
        try:
            for source, relative in zip(sources, paths):
                parts = relative.split("/")
                # Directory descriptors keep writes inside this upload even if a
                # concurrent process replaces an intermediate path with a link.
                parent_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    for part in parts[:-1]:
                        try:
                            os.mkdir(part, dir_fd=parent_fd)
                        except FileExistsError:
                            pass
                        next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                          dir_fd=parent_fd)
                        os.close(parent_fd)
                        parent_fd = next_fd
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                    output_fd = os.open(parts[-1], flags, 0o600, dir_fd=parent_fd)
                finally:
                    os.close(parent_fd)
                size = 0
                with os.fdopen(output_fd, "wb") as output:
                    while chunk := source.read(_CHUNK_BYTES):
                        size += len(chunk)
                        total += len(chunk)
                        if size > MAX_FILE_BYTES:
                            raise FileTooLarge("单个文件不能超过 25 MB")
                        if total > MAX_FOLDER_BYTES:
                            raise FileTooLarge("文件夹不能超过 100 MB")
                        output.write(chunk)
                if not size:
                    raise ValueError("文件夹内文件不能为空")
                sizes.append(size)
            record = {"id": identifier, "name": name, "filename": name,
                      "size": total, "count": len(paths), "kind": "folder",
                      "files": [{"path": path, "size": size} for path, size in zip(paths, sizes)]}
            with metadata.open("x", encoding="utf-8") as output:
                metadata_created = True
                json.dump(record, output, ensure_ascii=False)
            return {**record, "path": str(folder.resolve())}
        except BaseException:
            shutil.rmtree(folder)
            if metadata_created:
                metadata.unlink(missing_ok=True)
            raise

    def _get_folder(self, identifier: str) -> dict:
        metadata = self.root / f"{identifier}.folder.json"
        if metadata.is_symlink():
            raise FileNotFoundError("附件不存在")
        record = json.loads(metadata.read_text(encoding="utf-8"))
        folder = self.root / f"{identifier}.folder"
        if (record["id"] != identifier or record["kind"] != "folder"
                or not folder.is_dir() or folder.is_symlink()):
            raise ValueError("无效的附件元数据")
        files = record["files"]
        if (not isinstance(files, list) or not files or len(files) > MAX_FOLDER_FILES
                or record["count"] != len(files)):
            raise ValueError("无效的附件元数据")
        expected = {}
        for item in files:
            relative = _relative_path(item["path"])
            if (relative in expected or isinstance(item["size"], bool)
                    or not isinstance(item["size"], int) or item["size"] <= 0):
                raise ValueError("无效的附件元数据")
            expected[relative] = item["size"]
        found = {}
        for base, dirs, names in os.walk(folder, followlinks=False):
            for entry in dirs + names:
                path = Path(base) / entry
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise ValueError("文件夹内存在符号链接")
                if entry in dirs and not stat.S_ISDIR(info.st_mode):
                    raise ValueError("无效的附件目录")
                if entry in names:
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise ValueError("无效的附件文件")
                    found[path.relative_to(folder).as_posix()] = info.st_size
        if found != expected or sum(found.values()) != record["size"]:
            raise FileNotFoundError("附件不存在")
        return {**record, "path": str(folder.resolve())}

    def get(self, identifier: str) -> dict:
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
            raise FileNotFoundError("附件不存在")
        try:
            self._check_root()
            folder_metadata = self.root / f"{identifier}.folder.json"
            if folder_metadata.is_symlink() or folder_metadata.exists():
                return self._get_folder(identifier)
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
        return "\n".join(
            (f"文件夹附件：{file['filename']}，目录路径：{file['path']}" if file.get("kind") == "folder"
             else f"附件：{file['filename']}，路径：{file['path']}") for file in files
        ) + (f"\n\n{text}" if text else "")

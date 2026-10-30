"""Publish or inspect existing files through the shared session image store."""
from pathlib import Path

from ..core.cancellation import ExecutionContext
from ..storage.images import ImageStore
from .executor import _check, _read_path
from .result import ToolResult


def show_image(
    workspace: Path,
    images: ImageStore,
    path: str,
    context: ExecutionContext | None = None,
) -> ToolResult:
    _check(context)
    source = _read_path(workspace, path)
    image = images.add_file(source)
    _check(context)
    return ToolResult(images.markdown(image), [image])


def read_image(
    workspace: Path,
    images: ImageStore,
    path: str,
    context: ExecutionContext | None = None,
) -> ToolResult:
    _check(context)
    source = _read_path(workspace, path)
    image = images.find_file(source)
    image = image or images.add_file(source)
    if not images.path(image["id"]).is_file():
        raise FileNotFoundError("会话图片文件不存在")
    _check(context)
    return ToolResult(f"session_path: {images.path(image['id']).resolve()}", model_images=[image])

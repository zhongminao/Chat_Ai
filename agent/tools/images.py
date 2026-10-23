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
    text = f"图片已展示，报告可用 Markdown 引用：{images.markdown(image)}"
    return ToolResult(text, [image])


def read_image(
    workspace: Path,
    images: ImageStore,
    path: str,
    context: ExecutionContext | None = None,
    known_images: set[str] | None = None,
) -> ToolResult:
    _check(context)
    source = _read_path(workspace, path)
    image = images.find_file(source)
    known_images = known_images or set()
    image = image or images.add_file(source)
    if not images.path(image["id"]).is_file():
        raise FileNotFoundError("会话图片文件不存在")
    _check(context)
    text = f"图片已读取，仅供模型查看，尚未向用户展示\n{images.describe(image)}"
    return ToolResult(text, model_images=[image])

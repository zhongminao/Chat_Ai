"""Inspect existing files and return stable session image references."""
from pathlib import Path

from ..core.cancellation import ExecutionContext
from ..storage.images import ImageStore
from .executor import _check, _read_path
from .result import ToolResult


def read_image(
    workspace: Path,
    images: ImageStore,
    path: str,
    context: ExecutionContext | None = None,
) -> ToolResult:
    _check(context)
    source = _read_path(workspace, path)
    image = images.add_file(source)
    if not images.path(image["id"]).is_file():
        raise FileNotFoundError("会话图片文件不存在")
    _check(context)
    return ToolResult(f"session_path: {images.path(image['id']).resolve()}\nmarkdown: {images.markdown(image)}",
                      model_images=[image])

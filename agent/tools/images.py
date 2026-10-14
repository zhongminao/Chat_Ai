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
    name: str | None = None,
    context: ExecutionContext | None = None,
) -> ToolResult:
    _check(context)
    source = _read_path(workspace, path)
    image = images.add_file(source, name)
    _check(context)
    text = (f"图片已展示 ({image['width']} × {image['height']})\n"
            f"{images.describe(image)}\n来源：{source}")
    return ToolResult(text, [image])


def read_image(
    workspace: Path,
    images: ImageStore,
    path: str,
    context: ExecutionContext | None = None,
    known_images: set[str] | None = None,
    max_images: int | None = None,
) -> ToolResult:
    _check(context)
    source = _read_path(workspace, path)
    image = images.find_file(source)
    known_images = known_images or set()
    if (max_images is not None and len(known_images) >= max_images
            and (image is None or image["id"] not in known_images)):
        raise ValueError(f"当前视觉上下文最多包含 {max_images} 张不同图片；请使用新会话读取更多图片")
    image = image or images.add_file(source)
    if not images.path(image["id"]).is_file():
        raise FileNotFoundError("会话图片文件不存在")
    _check(context)
    text = (f"图片已读取，仅供模型查看，尚未向用户展示 ({image['width']} × {image['height']})\n"
            f"{images.describe(image)}\n来源：{source}")
    return ToolResult(text, model_images=[image])

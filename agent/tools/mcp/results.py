"""Convert MCP text and inline images into the existing session tool result."""
import base64
import hashlib
import json

from mcp import types

from ...storage.images import ImageStore, MAX_IMAGE_BYTES
from ..result import ToolResult


def _same_json(text: str, value) -> bool:
    try:
        return json.loads(text) == value
    except json.JSONDecodeError:
        return False


def convert_result(result: types.CallToolResult, images: ImageStore | None, *,
                   vision: bool = False, known_images: set[str] | None = None) -> str | ToolResult:
    texts = [item.text for item in result.content if item.type == "text"]
    if result.structured_content is not None:
        structured = json.dumps(result.structured_content, ensure_ascii=False)
        texts = [structured] + [text for text in texts if not _same_json(text, result.structured_content)]
    text = "\n".join(texts)
    if result.is_error:
        return "[mcp error] " + text
    blocks = [item for item in result.content if item.type == "image"]
    if not blocks:
        return text
    if images is None:
        raise ValueError("session image store is unavailable")

    saved = {item["sha256"]: item for item in images.list()
             if item.get("sha256") and images.path(item["id"]).is_file()}
    decoded = {}
    for block in blocks:
        if len(block.data) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
            raise ValueError("MCP image must not exceed 10 MiB")
        if block.mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError(f"unsupported MCP image type: {block.mime_type}")
        data = base64.b64decode(block.data, validate=True)
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise ValueError("MCP image must be nonempty and <= 10 MiB")
        digest = hashlib.sha256(data).hexdigest()
        asset = saved.get(digest)
        decoded[digest] = (data, block.mime_type)

    assets = []
    for digest, (data, mime) in decoded.items():
        extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime]
        asset = saved.get(digest) or images.add(data, f"mcp-{digest[:12]}.{extension}")
        assets.append(asset)
    receipts = "\n\n".join(images.describe(asset) for asset in assets)
    note = "MCP 图片已展示并提供给模型。" if vision else "MCP 图片已展示；当前模型未启用视觉，未附加图像内容。"
    return ToolResult("\n\n".join(part for part in (text, note, receipts) if part),
                      images=assets, model_images=assets if vision else [])

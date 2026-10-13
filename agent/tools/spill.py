import re
import uuid
from pathlib import Path


_SECRET = re.compile(
    r"(?i)(\b(?:api[_-]?key|token|secret|password)\b\s*[:=]\s*)([^\s,;]+)"
)


def _redact(text: str) -> str:
    return _SECRET.sub(r"\1[redacted]", text)


def handle(
    text: str,
    *,
    enabled: bool,
    max_inline_chars: int,
    preview_chars: int,
    workspace: Path,
    session_id: str,
    directory: str = ".spill",
) -> str:
    if not enabled or len(text) <= max_inline_chars:
        return text

    try:
        root = (workspace / directory / session_id).resolve()
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{uuid.uuid4().hex}.log"
        path.write_text(_redact(text), encoding="utf-8")
        relative = path.relative_to(workspace.resolve())
        preview = text[:preview_chars]
        return (
            f"{preview}\n\n"
            f"[spill] 完整输出已保存到 {relative}，共 {len(text)} 个字符。"
            " 如需继续查看，请使用 read_file 分页读取。"
        )
    except OSError:
        return text[:max_inline_chars] + "\n\n[spill] 保存失败，以上为截断内容。"

import re
import uuid
from pathlib import Path


_SECRET = re.compile(
    r"(?i)(\b(?:api[_-]?key|token|secret|password)\b\s*[:=]\s*)([^\s,;]+)"
)


def _redact(text: str) -> str:
    return _SECRET.sub(r"\1[redacted]", text)


def resolve_spill_directory(workspace: Path, directory: str) -> Path:
    if not isinstance(directory, str) or not directory.strip():
        raise ValueError("spill.directory 必须是非空路径")
    root = (workspace / Path(directory).expanduser()).resolve()
    if not root.is_relative_to(workspace.resolve()):
        raise ValueError("spill.directory 必须位于 workspace 内")
    return root


def elide_line(line: str, max_chars: int) -> str:
    if len(line) <= max_chars:
        return line
    marker = "...[cut]..."
    head = (max_chars - len(marker)) // 2
    return line[:head] + marker + line[-(max_chars - len(marker) - head):]


def preview_lines(lines: list[str], start: int, end: int, max_chars: int) -> str:
    return "\n".join(elide_line(line, max_chars) for line in lines[start:end])


def spill_tool_output(
    text: str,
    *,
    enabled: bool,
    max_inline_lines: int,
    head_lines: int,
    tail_lines: int,
    max_line_chars: int,
    workspace: Path,
    session_id: str,
    directory: str = ".spill",
) -> str:
    if not enabled:
        return text
    lines = text.splitlines()
    if len(lines) <= max_inline_lines and all(len(line) <= max_line_chars for line in lines):
        return text
    if max_inline_lines < 0 or head_lines < 0 or tail_lines < 0 or max_line_chars < 12:
        raise ValueError("invalid spill preview limits")

    saved = _redact(text)
    lines = saved.splitlines()
    total = len(lines)
    head = min(head_lines, total)
    tail = min(tail_lines, total - head)
    parts = []
    if head:
        parts.append(f"[spill] lines 1-{head} of {total}\n{preview_lines(lines, 0, head, max_line_chars)}")
    if total > head + tail:
        parts.append(f"[spill] {total - head - tail} lines omitted")
    if tail:
        start = total - tail
        parts.append(f"[spill] lines {start + 1}-{total} of {total}\n{preview_lines(lines, start, total, max_line_chars)}")
    preview = "\n".join(parts)

    try:
        root = (resolve_spill_directory(workspace, directory) / session_id).resolve()
        path = root / f"{uuid.uuid4().hex}.log"
        relative = path.relative_to(workspace.resolve())
        root.mkdir(parents=True, exist_ok=True)
        path.write_text(saved, encoding="utf-8")
        return f"{preview}\n[spill] Full output: {relative} ({total} lines). Use read_file with offset/limit."
    except (OSError, ValueError):
        return f"{preview}\n[spill] 保存失败，以上为截断内容。"

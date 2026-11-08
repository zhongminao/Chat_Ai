import re
import textwrap
import uuid
from pathlib import Path

from .result import TextSection


_SECRET = re.compile(
    r"(?i)(\b(?:api[_-]?key|token|secret|password)\b[\"']?\s*[:=]\s*)([\"']?)([^\s,;\"']+)"
)


def _redact(text: str) -> str:
    return _SECRET.sub(r"\1\2[redacted]", text)


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


def _bounded(text: str, chars: int) -> str:
    if len(text) <= chars:
        return text
    marker = "\n…[预览省略]"
    return text[:max(0, chars - len(marker))] + marker[:chars]


def _view_lines(text: str, width: int) -> list[str]:
    # Only the reading view is wrapped; the original text is saved separately.
    return [part for line in text.splitlines()
            for part in (textwrap.wrap(line, width=width, replace_whitespace=False,
                                       drop_whitespace=False) or [""])]


def _search_views(intro: str, sections: list[TextSection], width: int):
    lines = []
    cards = []
    for section in sections:
        start = len(lines) + 1
        lines.extend(_view_lines(section.header + "\n\n" + section.body, width))
        end = len(lines)
        lines.append("")
        cards.append((section.header, section.summary, f"正文视图行：{start}–{end}"))
    index = intro + "\n\n" + "\n\n".join("\n".join(card) for card in cards)
    body = "\n".join(lines)
    return cards, index, body


def _search_preview(intro: str, cards: list[tuple[str, str, str]], budget: int, width: int) -> str:
    # Allocate a fair share per result instead of consuming the budget on result 1.
    intro = _bounded(intro, min(1600, budget // 4))
    remaining = max(0, budget - len(intro) - 200)
    per_card = min(1000, remaining // max(1, len(cards)) - 2)
    if per_card < 160:
        return intro + "\n候选较多，完整候选目录及命中摘录请读取下方索引文件。"
    rendered = []
    for header, summary, location in cards:
        # Long URLs/titles cannot displace every excerpt or its full-text locator.
        header_budget = min(300, per_card // 3)
        summary_budget = max(0, per_card - header_budget - len(location) - 3)
        rendered.append(_bounded(header, header_budget) + "\n"
                        + _bounded(summary, summary_budget) + "\n" + location)
    return "\n".join(_view_lines(intro + "\n\n" + "\n\n".join(rendered), width))


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
    max_inline_chars: int = 20000,
    max_preview_chars: int = 16000,
    preview: str | None = None,
    sections: list[TextSection] | None = None,
) -> str:
    if (max_inline_lines < 0 or head_lines < 0 or tail_lines < 0 or max_line_chars < 12
            or max_inline_chars < 512 or max_preview_chars < 512):
        raise ValueError("invalid spill preview limits")
    search = preview is not None
    width = min(1000, max_line_chars)
    cards, index, body = [], "", ""
    if search:
        safe_sections = [TextSection(_redact(s.header), _redact(s.summary), _redact(s.body))
                         for s in sections or []]
        cards, index, body = _search_views(_redact(preview), safe_sections, width)
        inline = index + ("\n\n[完整段落]\n" + body if body else "")
    else:
        inline = text
    if not enabled:
        return inline
    lines = inline.splitlines()
    if (len(lines) <= max_inline_lines and len(inline) <= max_inline_chars
            and len(text) <= max_inline_chars
            and all(len(line) <= max_line_chars for line in lines)):
        return inline

    saved = _redact(text)
    total = len(saved.splitlines())
    if search:
        excerpt = _search_preview(_redact(preview), cards, max_preview_chars - 200, width)
    else:
        lines = saved.splitlines()
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
        excerpt = _bounded("\n".join(parts), max_preview_chars - 200)

    try:
        root = (resolve_spill_directory(workspace, directory) / session_id).resolve()
        identifier = uuid.uuid4().hex
        path = root / f"{identifier}.log"
        relative = path.relative_to(workspace.resolve())
        root.mkdir(parents=True, exist_ok=True)
        path.write_text(saved, encoding="utf-8")
        if search:
            view_path = root / f"{identifier}.view.txt"
            index_path = root / f"{identifier}.index.txt"
            view_path.write_text(body, encoding="utf-8")
            # Wrap the directory too: no JSON-escaped newlines or unpageable paragraphs.
            index_path.write_text("\n".join(_view_lines(index, width)), encoding="utf-8")
            receipt = (f"\n[spill] 查询相关摘录预览；正文未完整展示。\n"
                       f"候选完整索引：{index_path.relative_to(workspace.resolve())}\n"
                       f"正文视图：{view_path.relative_to(workspace.resolve())}（{len(body.splitlines())} 行；各条行号见上方）\n"
                       f"完整原始结果（脱敏）：{relative}（{total} 行，{len(saved)} 字符）\n"
                       "使用 read_file(path=索引或正文视图路径, offset=行号, limit=10) 按需读取。")
            excerpt = _search_preview(_redact(preview), cards,
                                      max(0, max_preview_chars - len(receipt)), width)
        else:
            receipt = f"\n[spill] Full output: {relative} ({total} lines). Use read_file with offset/limit."
        return _bounded(excerpt, max(0, max_preview_chars - len(receipt))) + receipt
    except (OSError, ValueError):
        return _bounded(excerpt, max_preview_chars - 80) + "\n[spill] 保存失败，以上为截断内容；完整内容定位不可用。"

"""Query-focused, extractive search views; spill owns persistence and budgets."""
from __future__ import annotations

import json
import re

from .result import TextSection, ToolResult


DEFAULT_CONTEXT_CHARS = 200
_SENTENCE_END = re.compile(r"[.!?。！？；;\n]")


_STOP_WORDS = {"a", "an", "and", "are", "for", "in", "is", "of", "on", "the", "to", "with",
               "什么", "怎么", "如何", "哪些", "帮我", "请问", "一下", "关于", "以及", "进行"}


def query_terms(query: str) -> list[str]:
    """Keep identifiers intact; use overlapping Chinese phrases without dependencies."""
    terms = []
    for token in re.findall(r"[a-zA-Z0-9_][a-zA-Z0-9_.+-]*|[\u4e00-\u9fff]+", query):
        token = token.lower()
        if token in _STOP_WORDS:
            continue
        candidates = [token]
        if re.fullmatch(r"[\u4e00-\u9fff]{3,}", token):
            candidates.extend(token[i:i + 2] for i in range(len(token) - 1))
        for value in candidates:
            if value not in _STOP_WORDS and value not in terms:
                terms.append(value)
    return terms[:64]


def extract_context(
    text: str, terms: list[str], context_chars: int = DEFAULT_CONTEXT_CHARS,
) -> tuple[list[str], str]:
    """Quote at most three windows, preferring coverage of distinct query terms."""
    matches = []
    for term in terms:
        match = re.search(re.escape(term), text, flags=re.IGNORECASE)
        if match:
            matches.append((term, match.start()))
    windows = []
    for term, at in sorted(matches, key=lambda item: (-len(item[0]), item[1])):
        start, end = max(0, at - context_chars), min(len(text), at + len(term) + context_chars)
        # Extend outward by at most 60 characters to avoid cutting nearby sentences.
        before = list(_SENTENCE_END.finditer(text, max(0, start - 60), start))
        if before:
            start = before[-1].end()
        after = _SENTENCE_END.search(text, end, min(len(text), end + 60))
        if after:
            end = after.end()
        if any(start < right and end > left for left, right in windows):
            continue
        windows.append((start, end))
        if len(windows) == 3:
            break
    excerpts = [
        ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")
        for start, end in sorted(windows)
    ]
    return [term for term, _ in matches], "\n".join(excerpts)


def _string(value) -> str:
    return value if isinstance(value, str) else ""


def web_search_output(
    text: str, query: str, *, context_chars: int = DEFAULT_CONTEXT_CHARS,
) -> str | ToolResult:
    """Adapt only recognized web-search JSON; unknown MCP outputs stay untouched."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return text
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        return text
    rows = data["results"]
    if not all(isinstance(row, dict) and isinstance(row.get("url"), str) for row in rows):
        return text
    terms = query_terms(query)
    sections = []
    for index, row in enumerate(rows, 1):
        title = _string(row.get("title")) or "（无标题）"
        content = _string(row.get("content"))
        snippet = _string(row.get("snippet"))
        upstream_summary = _string(row.get("summary"))
        # Search source text, not a generated upstream summary, for original quotes.
        source = content or snippet
        matched, excerpt = extract_context(source, terms, context_chars)
        if not excerpt:
            excerpt = "无正文/片段字面命中；以下仅为来源开头：\n" + source[:240]
        header = f"[R{index}] {title}\nURL：{row['url']}"
        metadata = "\n".join(f"{key}：{row[key]}" for key in
                             ("site_name", "date", "rerank_score", "authority")
                             if row.get(key) is not None)
        body = "\n\n".join(part for part in (
            metadata,
            "[来源正文]\n" + content if content else "[来源正文未提供]",
            "[上游片段]\n" + snippet if snippet else "",
            "[上游摘要，非原文摘录]\n" + upstream_summary if upstream_summary else "",
        ) if part)
        summary = "原文摘录：\n" + excerpt + "\n正文/片段命中：" + ("、".join(matched) or "无")
        sections.append(TextSection(header, summary, body))
    intro = (f"网页搜索：{query}\n后端：{data.get('backend', 'unknown')}；实际返回 {len(rows)} 条。\n"
             "以下为查询相关的来源原文摘录，不是全文或模型总结；保留上游结果顺序。")
    if data.get("unresponsive_engines"):
        intro += "\n部分引擎不可用：" + json.dumps(data["unresponsive_engines"], ensure_ascii=False)
    return ToolResult(text, preview=intro, sections=sections)


def resource_search_output(text: str, query: str) -> ToolResult:
    data = json.loads(text)
    sections = []
    terms = query_terms(query)
    for index, row in enumerate(data.get("results", []), 1):
        usage = row["usage"]
        matched, excerpt = extract_context(usage, terms)
        reasons = "、".join(row["match_reasons"])
        header = f"[S{index}] {row['skill_id']}\n说明文件：{row['instructions_path']}"
        summary = ("原文摘录：\n" + (excerpt or "无正文字面命中；用途说明：" + row["description"])
                   + f"\n元数据匹配：{reasons}\n正文命中：{'、'.join(matched) or '无'}")
        metadata = {key: value for key, value in row.items() if key != "usage"}
        body = "[元数据]\n" + json.dumps(metadata, ensure_ascii=False, indent=2) + "\n\n[完整 Skill 说明]\n" + usage
        sections.append(TextSection(header, summary, body))
    intro = (f"本地资源搜索：{query}\n返回 {len(sections)} 项；仅匹配 manifest 元数据，未搜索 references 全文。\n"
             "摘录只用于选择 Skill；执行前必须读取完整说明及当前步骤需要的参考资料，不得以摘录代替规则。")
    if data.get("message"):
        intro += "\n" + data["message"]
    return ToolResult(text, preview=intro, sections=sections)

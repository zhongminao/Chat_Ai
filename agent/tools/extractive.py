"""Small, dependency-free, query-focused excerpts (never generated summaries)."""
from __future__ import annotations

import re


_CJK = re.compile(r"[\u3400-\u9fff]")
_ASCII_WORD = r"A-Za-z0-9_"
_NAV_LABELS = {
    "home", "menu", "navigation", "contents", "table of contents", "next",
    "previous", "back", "login", "log in", "sign in", "subscribe", "search",
    "privacy policy", "terms of use", "skip to content", "read more",
    "首页", "导航", "目录", "上一页", "下一页", "登录", "注册", "返回顶部",
    "隐私政策", "联系我们", "更多", "参考文献", "references", "bibliography",
}
_ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "vs", "etc",
                  "fig", "no", "e.g", "i.e", "et al"}
_END = re.compile(r'[。！？!?；;]+[”’"\')）]*|\.+[”’"\')）]*(?=\s|$)')


def _patterns(terms: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    result = []
    seen = set()
    for raw in terms:
        term = raw.strip()
        key = term.casefold()
        if not term or key in seen:
            continue
        seen.add(key)
        expression = re.escape(term)
        # ASCII boundaries, not Unicode \b: Chinese prose can abut an acronym.
        # Chinese query phrases intentionally retain substring semantics.
        if re.search(r"[A-Za-z0-9_]", term) and not _CJK.search(term):
            expression = rf"(?<![{_ASCII_WORD}]){expression}(?![{_ASCII_WORD}])"
        result.append((term, re.compile(expression, re.IGNORECASE)))
    return result


def _noise(line: str) -> bool:
    if not line or re.match(r"^#{1,6}(?:\s|$)", line):
        return True
    if re.fullmatch(r"[-_*\s=]{3,}", line) or line.startswith(("|", "![")):
        return True
    if line.casefold().strip(" :：.!。") in _NAV_LABELS:
        return True
    # Link-only lines and menus of short labels are not prose.
    if re.fullmatch(r"(?:https?://\S+|\[[^\]]+\]\([^)]*\))", line):
        return True
    parts = re.split(r"\s*[|›»]\s*|\s+[>»]\s+", line)
    if len(parts) >= 2 and all(len(part) <= 32 for part in parts):
        return True
    if re.match(r"^(?:\[\d+\]|\[\^\w+\]:)", line):
        return True
    if re.match(r"^\d+[.)]\s+", line) and re.search(
        r"\bet al\b|\bdoi\b|\b(?:19|20)\d{2}\b|https?://", line, re.I
    ):
        return True
    if re.match(r"^(?:doi\s*:|\\(?:begin|end|frac|sum)\b)", line, re.I):
        return True
    if line.startswith(("$", r"\[", r"\(")):
        return True
    # A short symbolic equation, but not ordinary prose containing '='.
    if len(line) < 160 and re.match(r"^[A-Za-z][A-Za-z0-9_^]*(?:\([^)]*\))?\s*=", line):
        return True
    if re.search(r"[=∑∫]", line):
        words = re.findall(r"[A-Za-z]{3,}|[\u3400-\u9fff]{2,}", line)
        if not words and len(line) < 160:
            return True
    return not re.search(r"[A-Za-z0-9\u3400-\u9fff]", line)


def _sentences(text: str) -> list[str]:
    result = []
    seen = set()
    fence = None
    in_math = False
    for raw in text.splitlines():
        line = raw.strip()
        marker = re.match(r"^(`{3,}|~{3,})", line)
        if marker:
            char = marker.group()[0]
            if fence is None:
                fence = char
            elif fence == char:
                fence = None
            continue
        if fence:
            continue
        if line in ("$$", r"\[", r"\]"):
            in_math = not in_math
            continue
        if in_math or _noise(line):
            continue
        start = 0
        for match in _END.finditer(line):
            punctuation = match.group()
            if punctuation.startswith("."):
                prefix = line[:match.start()]
                token = re.search(r"([A-Za-z][A-Za-z.]*|et al)$", prefix)
                if token and (token.group().lower() in _ABBREVIATIONS or
                              re.fullmatch(r"(?:[A-Za-z]\.)*[A-Za-z]", token.group())):
                    continue
            sentence = line[start:match.end()].strip()
            if sentence:
                result.append(sentence)
            start = match.end()
        tail = line[start:].strip()
        if tail:
            result.append(tail)
    unique = []
    for sentence in result:
        key = re.sub(r"\s+", " ", sentence).casefold().rstrip(".!?。！？；;")
        if key not in seen and not _noise(sentence):
            seen.add(key)
            unique.append(sentence)
    return unique


def _hits(text: str, patterns: list[tuple[str, re.Pattern[str]]]) -> set[int]:
    return {i for i, (_, pattern) in enumerate(patterns) if pattern.search(text)}


def _clip(text: str, patterns: list[tuple[str, re.Pattern[str]]], budget: int) -> str:
    if len(text) <= budget:
        return text
    if budget <= 1:
        return "…" if budget == 1 else ""
    matches = [match for _, pattern in patterns if (match := pattern.search(text))]
    if not matches:
        return text[:budget - 1].rstrip() + "…"
    first = min(matches, key=lambda match: match.start())
    start = max(0, first.start() - max(0, budget - 2 - len(first.group())) // 2)
    end = min(len(text), start + budget - bool(start) - 1)
    if end == len(text) - 1:
        end = len(text)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def extract_brief(text: str, terms: list[str], max_chars: int = 200) -> tuple[list[str], str]:
    """Return ``(matched_terms, brief)`` using at most two original sentences.

    Rank by distinct, case-insensitive query terms (ASCII word boundaries;
    Chinese substrings). Add a second sentence only for new term coverage,
    restore source order, and prefer complete sentences within the budget.
    Long sentences are clipped around keywords with explicit ``…`` markers.
    The budget includes those markers and the single-space sentence separator.
    ``matched_terms`` preserves input spelling/order, deduplicates case-insensitively,
    and describes only terms actually present in the returned excerpt.

    With no hits, use the first non-noise sentence. Empty/noise-only input or a
    nonpositive budget returns ``([], '')``. Filtering is heuristic, not a full
    Markdown, bibliography, or mathematical-expression parser. No I/O or models.
    """
    if max_chars <= 0 or not text.strip():
        return [], ""
    sentences = _sentences(text)
    if not sentences:
        return [], ""
    patterns = _patterns(terms)
    coverage = [_hits(sentence, patterns) for sentence in sentences]
    first = max(range(len(sentences)), key=lambda i: (len(coverage[i]), -i))
    if not coverage[first]:
        return [], _clip(sentences[0], [], max_chars)

    primary = _clip(sentences[first], patterns, max_chars)
    pieces = [(first, primary)]
    primary_hits = _hits(primary, patterns)
    others = [i for i in range(len(sentences)) if coverage[i] - primary_hits and i != first]
    if others and len(sentences[first]) <= max_chars:
        second = max(others, key=lambda i: (len(coverage[i] - primary_hits), len(coverage[i]), -i))
        remaining = max_chars - len(primary) - 1
        # Never replace a complete best sentence by two incomplete fragments.
        if remaining > 0:
            new_patterns = [item for i, item in enumerate(patterns) if i not in primary_hits]
            extra = _clip(sentences[second], new_patterns, remaining)
            if _hits(extra, patterns) - primary_hits:
                pieces.append((second, extra))
    brief = " ".join(piece for _, piece in sorted(pieces))
    matched = _hits(brief, patterns)
    return [term for i, (term, _) in enumerate(patterns) if i in matched], brief

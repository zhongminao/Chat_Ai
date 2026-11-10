"""Read-only search over registered local skills and future knowledge indexes."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shlex
import sys
from typing import Any

import yaml

_MAX_TOP_K = 10


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _fields(raw: dict[str, Any], field: str) -> tuple[str, ...]:
    triggers = raw.get("triggers") or {}
    return _strings(raw.get(field)) + _strings(triggers.get(field))


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(term for term in re.findall(r"[a-z0-9_.+-]+|[\u4e00-\u9fff]+", text.casefold())
                 if term)


def _match(query: str, raw: dict[str, Any]) -> tuple[int, list[str]]:
    text = query.casefold()
    name = str(raw.get("name", "")).casefold()
    description = str(raw.get("description", "")).casefold()
    triggers = raw.get("triggers") or {}
    extensions = _fields(raw, "extensions")
    mime_types = _fields(raw, "mime_types")
    intents = _fields(raw, "intents")
    aliases = _fields(raw, "aliases")
    capabilities = _fields(raw, "capabilities")
    excludes = _fields(raw, "excludes") + _strings(raw.get("excludes"))

    for phrase in excludes:
        if phrase.casefold() in text:
            return 0, [f"excluded:{phrase}"]

    score = 0
    reasons: list[str] = []

    if name and name in text:
        score += 80
        reasons.append(f"name:{name}")
    for extension in extensions:
        value = extension.casefold()
        if value and value in text:
            score += 100
            reasons.append(f"extension:{extension}")
    for mime_type in mime_types:
        value = mime_type.casefold()
        if value and value in text:
            score += 100
            reasons.append(f"mime_type:{mime_type}")
    for alias in aliases:
        value = alias.casefold()
        if value and value in text:
            score += 45
            reasons.append(f"alias:{alias}")
    for capability in capabilities:
        value = capability.casefold()
        if value and value in text:
            score += 35
            reasons.append(f"capability:{capability}")
    for intent in intents:
        value = intent.casefold()
        if value and value in text:
            score += 30
            reasons.append(f"intent:{intent}")

    searchable = " ".join([name, description, *extensions, *mime_types, *intents,
                            *aliases, *capabilities]).casefold()
    overlap = []
    for token in _tokens(text):
        if token in searchable and token not in overlap:
            overlap.append(token)
    if overlap:
        score += min(20, 5 * len(overlap))
        reasons.extend(f"term:{token}" for token in overlap[:4])
    return score, reasons


def _package(
    root: Path,
    manifest: Path,
    raw: dict[str, Any],
    score: int,
    reasons: list[str],
) -> dict[str, Any]:
    package = manifest.parent.resolve()
    entrypoint = (package / str(raw.get("entrypoint", "SKILL.md"))).resolve()
    if not entrypoint.is_file() or package not in entrypoint.parents:
        raise ValueError(f"skill entrypoint is invalid: {manifest}")
    usage = entrypoint.read_text(encoding="utf-8")
    usage = usage.replace("{{python}}", shlex.quote(sys.executable))
    usage = usage.replace("{{skill_dir}}", shlex.quote(str(package)))
    scripts_dir = package / "scripts"
    scripts = sorted(
        str(path.resolve())
        for path in scripts_dir.glob("*")
        if path.is_file() and path.suffix in {".sh", ".py"}
    ) if scripts_dir.is_dir() else []
    references = [
        str((package / value).resolve())
        for value in _strings(raw.get("references"))
        if (package / value).is_file()
    ]
    return {
        "skill_id": str(raw["name"]),
        "version": str(raw.get("version", "")),
        "score": score,
        "match_reasons": reasons,
        "description": str(raw.get("description", "")),
        "delivery": str(raw.get("delivery", "search_result")),
        "manifest_path": str(manifest.resolve()),
        "instructions_path": str(entrypoint),
        "scripts": scripts,
        "references": references,
        "usage": usage,
    }


def search_resources(
    workspace: Path,
    query: str,
    resource_type: str = "skill",
    top_k: int = 5,
) -> str:
    """Return matching skill usage; knowledge search is reserved for a later index."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be non-empty")
    if resource_type not in {"skill", "knowledge"}:
        raise ValueError("resource_type must be skill or knowledge")
    if type(top_k) is not int or top_k < 1 or top_k > _MAX_TOP_K:
        raise ValueError("top_k must be an integer from 1 to 10")

    if resource_type == "knowledge":
        return json.dumps({
            "resource_type": "knowledge",
            "query": query,
            "results": [],
            "message": "knowledge index is not configured yet",
        }, ensure_ascii=False, indent=2)

    skills_root = (workspace.parent / "skills").resolve()
    if not skills_root.is_dir():
        return json.dumps({
            "resource_type": "skill",
            "query": query,
            "results": [],
            "message": f"skill directory not found: {skills_root}",
        }, ensure_ascii=False, indent=2)

    matches: list[tuple[int, Path, dict[str, Any], list[str]]] = []
    for manifest in sorted(skills_root.glob("*/manifest.yaml")):
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            continue
        score, reasons = _match(query, raw)
        # Token overlap is a weak relevance hint, not evidence of an actual
        # skill trigger. Do not let coincidental words fill the top-k slots.
        if score and any(not reason.startswith("term:") for reason in reasons):
            matches.append((score, manifest, raw, reasons))
    matches.sort(key=lambda item: (-item[0], str(item[1])))
    results = [_package(skills_root, manifest, raw, score, reasons)
               for score, manifest, raw, reasons in matches[:top_k]]
    return json.dumps({
        "resource_type": "skill",
        "query": query,
        "results": results,
    }, ensure_ascii=False, indent=2)

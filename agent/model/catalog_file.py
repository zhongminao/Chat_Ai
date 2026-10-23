"""Patch active model lists without reserializing user comments or provider blocks."""
import os
import tempfile
from pathlib import Path

import yaml


def write_models(path: Path, updates: dict) -> None:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    document = yaml.compose(original)
    patches = []
    providers = next(value for key, value in document.value if key.value == "providers")
    for key, provider in providers.value:
        if key.value not in updates:
            continue
        for field, models in provider.value:
            if field.value != "models":
                continue
            # Collection end marks can include following comments: only consume
            # through the last scalar, leaving commented-out providers untouched.
            def last_line(node):
                if isinstance(node, yaml.ScalarNode):
                    return node.end_mark.line
                children = ([part for pair in node.value for part in pair]
                            if isinstance(node, yaml.MappingNode) else node.value)
                return max((last_line(child) for child in children), default=node.start_mark.line)

            start, end = field.start_mark.line, last_line(models) + 1
            indent = field.start_mark.column
            replacement = yaml.safe_dump({"models": updates[key.value]}, allow_unicode=True,
                                         sort_keys=False).splitlines(keepends=True)
            replacement = [" " * indent + line for line in replacement]
            comments = [line for line in lines[start:end]
                        if not line.strip() or line.lstrip().startswith("#")]
            # Preserve inline comments, including quoted scalars containing '#'.
            for line in lines[start:end]:
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                quote = None
                escaped = False
                for index, char in enumerate(line):
                    if escaped:
                        escaped = False
                    elif char == "\\" and quote == '"':
                        escaped = True
                    elif char in "\"'":
                        if quote == char:
                            quote = None
                        elif quote is None:
                            quote = char
                    elif char == "#" and quote is None and index and line[index - 1].isspace():
                        comments.append(" " * indent + line[index:])
                        break
            patches.append((start, end, replacement + comments))
    for start, end, replacement in reversed(patches):
        lines[start:end] = replacement
    updated = "".join(lines)
    if updated == original:
        return
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            target.write(updated)
            target.flush()
            os.fsync(target.fileno())
        if path.read_text(encoding="utf-8") != original:
            raise RuntimeError("providers.yaml changed during refresh; refusing to overwrite")
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

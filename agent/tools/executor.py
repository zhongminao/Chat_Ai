import os
import selectors
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from ..core.cancellation import ExecutionContext, RunCancelled


DEFAULT_TIMEOUT = 30


def _path(root: Path, value: str) -> Path:
    target = (root / value).resolve()
    if target != root and root not in target.parents:
        raise ValueError("path is outside workspace")
    return target


def _read_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _check(context: ExecutionContext | None) -> None:
    if context:
        context.cancellation.raise_if_cancelled()


def read_file(
    root: Path,
    path: str,
    offset: int = 0,
    limit: int = 12000,
    context: ExecutionContext | None = None,
) -> str:
    if offset < 0 or limit <= 0:
        raise ValueError("offset must be >= 0 and limit must be > 0")
    _check(context)
    text = _read_path(root, path).read_text(encoding="utf-8")
    _check(context)
    return text[offset:offset + limit]


def _atomic_write(target: Path, content: str, context: ExecutionContext | None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            for start in range(0, len(content), 65536):
                _check(context)
                stream.write(content[start:start + 65536])
            stream.flush()
            os.fsync(stream.fileno())
        _check(context)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def write_file(
    root: Path,
    path: str,
    content: str,
    context: ExecutionContext | None = None,
) -> str:
    target = _path(root, path)
    _atomic_write(target, content, context)
    return f"wrote {path}"


def edit_file(
    root: Path,
    path: str,
    old: str,
    new: str,
    context: ExecutionContext | None = None,
) -> str:
    target = _path(root, path)
    _check(context)
    content = target.read_text(encoding="utf-8")
    if content.count(old) != 1:
        raise ValueError("old text must occur exactly once")
    _atomic_write(target, content.replace(old, new), context)
    return f"edited {path}"


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_bash(
    root: Path,
    command: str,
    context: ExecutionContext | None = None,
) -> str:
    _check(context)
    process = subprocess.Popen(
        command,
        shell=True,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    remove_callback = (
        context.cancellation.add_callback(lambda: _terminate(process))
        if context else lambda: None
    )
    selector = selectors.DefaultSelector()
    output = bytearray()
    deadline = time.monotonic() + DEFAULT_TIMEOUT
    try:
        assert process.stdout is not None
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            _check(context)
            if time.monotonic() >= deadline:
                _terminate(process)
                raise subprocess.TimeoutExpired(command, DEFAULT_TIMEOUT)
            ready = selector.select(timeout=0.2)
            if ready:
                chunk = os.read(process.stdout.fileno(), 65536)
                if chunk:
                    output.extend(chunk)
                else:
                    selector.unregister(process.stdout)
            if process.poll() is not None and not selector.get_map():
                break
        _check(context)
        return output.decode(errors="replace") or f"exit code: {process.returncode}"
    except RunCancelled:
        _terminate(process)
        raise
    finally:
        selector.close()
        remove_callback()
        if process.poll() is None:
            _terminate(process)
        process.wait()


def execute(
    root: Path,
    name: str,
    arguments: dict[str, Any],
    context: ExecutionContext | None = None,
) -> str:
    functions = {
        "read_file": read_file,
        "write_file": write_file,
        "edit_file": edit_file,
        "run_bash": run_bash,
    }
    if name not in functions:
        raise ValueError(f"unknown tool: {name}")
    try:
        return functions[name](root, context=context, **arguments)
    except RunCancelled:
        raise
    except Exception as exc:
        return f"[tool error] {type(exc).__name__}: {exc}"

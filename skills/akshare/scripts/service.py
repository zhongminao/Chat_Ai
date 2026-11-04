#!/usr/bin/env python3
"""Run the local Skill MCP in the same Python environment as the Agent."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import importlib.metadata
import importlib.util
import signal
import subprocess
import sys
import time
import urllib.request

SKILL = Path(__file__).resolve().parents[1]
INSTANCE = hashlib.sha256(str(SKILL).encode()).hexdigest()[:16]


def locations():
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return Path(sys.prefix), state / "chat-ai/akshare" / INSTANCE



@contextlib.contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a") as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        yield


def process_stamp(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def owned(record):
    pid = record.get("pid")
    if type(pid) is not int or pid <= 1 or not record.get("stamp"):
        return False
    try:
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        return (process_stamp(pid) == record["stamp"]
                and str(SKILL / "scripts/server.py").encode() in argv
                and INSTANCE.encode() in argv)
    except OSError:
        return False


def read_record(state):
    try:
        result = json.loads((state / "service.json").read_text())
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def status(state):
    record = read_record(state)
    if not owned(record):
        return {"running": False}
    port = record.get("port")
    if type(port) is not int or not 1 <= port <= 65535:
        return {"running": False, "reason": "service is starting or unresponsive"}
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/healthz", timeout=1) as response:
            health = json.load(response)
        if health.get("instance") != INSTANCE or health.get("pid") != record["pid"]:
            return {"running": False, "reason": "endpoint identity does not match"}
        return {"running": True, "pid": record["pid"],
                "url": f"http://127.0.0.1:{port}/mcp",
                "idle_seconds": health["idle_seconds"]}
    except (OSError, ValueError, KeyError):
        return {"running": False, "reason": "service is unresponsive"}


def prepare(environment):
    missing = [name for name in ["akshare", "aktools", "mcp", "uvicorn"]
               if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError("当前项目环境缺少依赖：" + ", ".join(missing) + "；请部署时统一安装项目 requirements.txt，然后重新启动。")
    mcp_version = tuple(int(part) for part in importlib.metadata.version("mcp").split(".")[:2])
    if not (2, 3) <= mcp_version < (3, 0):
        raise RuntimeError("AKTools 需要 mcp>=2.3.0,<3；请部署时统一安装项目 requirements.txt。")
    return Path(sys.executable)


def stop(state):
    record = read_record(state)
    if owned(record):
        os.kill(record["pid"], signal.SIGTERM)
        for _ in range(100):
            if not owned(record):
                break
            time.sleep(0.05)
        if owned(record):
            os.kill(record["pid"], signal.SIGKILL)
    (state / "service.json").unlink(missing_ok=True)
    return {"running": False, "stopped": True}


def start(environment, state, idle_seconds):
    current = status(state)
    if current["running"]:
        return {**current, "reused": True}
    if owned(read_record(state)):
        raise RuntimeError("Existing skill process is unresponsive; run stop before restarting")
    python = prepare(environment)
    logfile = state / "server.log"
    if logfile.exists() and logfile.stat().st_size > 2_000_000:
        logfile.replace(state / "server.previous.log")
    with logfile.open("a") as output:
        process = subprocess.Popen(
            [str(python), "-B", str(SKILL / "scripts/server.py"),
             "--state-dir", str(state), "--instance", INSTANCE,
             "--idle-seconds", str(idle_seconds)],
            cwd=state, stdin=subprocess.DEVNULL, stdout=output,
            stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    for _ in range(150):
        if process.poll() is not None:
            raise RuntimeError(f"MCP process exited; see {logfile}")
        current = status(state)
        if current["running"]:
            return {**current, "reused": False}
        time.sleep(0.1)
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    raise RuntimeError(f"MCP did not become ready; see {logfile}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["setup", "start", "status", "stop"])
    parser.add_argument("--idle-seconds", type=int, default=900)
    args = parser.parse_args()
    if sys.version_info < (3, 11) or sys.maxsize <= 2**32:
        parser.error("Use 64-bit Python 3.11 or newer")
    if args.idle_seconds < 1:
        parser.error("idle-seconds must be positive")
    environment, state = locations()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with locked(state / "manager.lock"):
            if args.action == "setup":
                result = {"ready": True, "python": str(prepare(environment))}
            elif args.action == "start":
                result = start(environment, state, args.idle_seconds)
            elif args.action == "stop":
                result = stop(state)
            else:
                result = status(state)
        print(json.dumps({**result, "state": "ready" if result.get("running") else "stopped",
                          "python": sys.executable, "skill_dir": str(SKILL),
                          "state_dir": str(state)}, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"running": False, "state": "failed", "error": str(error),
                          "python": sys.executable, "state_dir": str(state)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

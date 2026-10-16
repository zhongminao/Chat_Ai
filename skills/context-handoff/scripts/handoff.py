"""Freeze a chat_ai handoff and start it through the existing Web API."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def request(base, path, data=None, method=None):
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(data, ensure_ascii=False).encode() if data is not None else None,
        headers={"Content-Type": "application/json"}, method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def count_tokens(messages, model_url, tools=None):
    body = {"messages": messages, "add_generation_prompt": True}
    if tools:
        body["tools"] = tools
    prompt = request(model_url, "/apply-template", body)["prompt"]
    return len(request(model_url, "/tokenize", {"content": prompt, "add_special": False})["tokens"])


def group_messages(messages):
    """Keep every assistant tool call with all its replies as one selectable unit."""
    groups = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if message["role"] in {"system", "user"}:
            index += 1
            continue
        if message["role"] != "assistant":
            raise ValueError("Orphan tool reply in source history")
        block = [message]
        pending = {call["id"] for call in message.get("tool_calls", [])}
        index += 1
        while pending:
            if index >= len(messages):
                raise ValueError("Incomplete source tool group")
            reply = messages[index]
            call_id = reply.get("tool_call_id")
            if reply["role"] != "tool" or call_id not in pending:
                raise ValueError("Mismatched source tool group")
            block.append(reply)
            pending.remove(call_id)
            index += 1
        groups.append({"id": f"g{len(groups) + 1:04d}", "messages": block})
    return groups


def prepare(args):
    project = args.project.resolve()
    sys.path.insert(0, str(project))
    from agent.core.agent_factory import build_state
    from agent.storage.event_log import EventLog
    from agent.storage.session import SessionStore
    from agent.workflow.config import load
    from agent.tools.mcp.client import McpClient
    from agent.tools.schema import TOOL_SCHEMAS, DELEGATE_SCHEMA, WATCH_SCHEMA, SUBMIT_SCHEMA

    config = load(project / "config.yaml")
    store = SessionStore(config.event_log.parent)
    listed = request(args.api, "/api/sessions")["sessions"]
    source = next(item for item in listed if item["id"] == args.session)
    if source["busy"]:
        raise ValueError("Wait until the source session is idle before freezing it")
    log_path = store.path(args.session) / "events.jsonl"
    raw = log_path.read_bytes()
    records = EventLog(log_path).read()
    state = build_state(config, store.metadata(args.session), records)
    if state["role"] != "main":
        raise ValueError("This experiment resumes main sessions only")
    if any(message.get("images") or message.get("model_images") for message in state["messages"]):
        raise ValueError("This text-only experiment does not transfer image attachments")
    workspace = args.workspace.resolve()
    if not workspace.is_dir():
        raise ValueError("Workspace must be an existing task directory")
    inventory = [
        {"path": str(path.relative_to(workspace)), "bytes": path.stat().st_size}
        for path in sorted(workspace.rglob("*"))
        if path.is_file() and not path.is_symlink()
        and not any(part in {"node_modules", ".git", "__pycache__"} for part in path.relative_to(workspace).parts)
    ]
    tools = [*TOOL_SCHEMAS, *(McpClient(config.mcp).schemas if config.mcp else []),
             DELEGATE_SCHEMA, WATCH_SCHEMA, SUBMIT_SCHEMA]
    snapshot = {
        "version": 1, "source_session_id": args.session,
        "source_seq": records[-1]["seq"] if records else 0,
        "source_events_sha256": digest(raw), "workspace": str(workspace),
        "model": state["model"], "messages": state["messages"], "tools": tools,
        "users": [{"seq": e["seq"], "content": e["prompt"]}
                  for e in records if e["type"] == "turn.started"],
        "groups": group_messages(state["messages"]), "file_inventory": inventory,
        "message_tokens": count_tokens(state["messages"], args.model_url),
        "request_tokens": count_tokens(state["messages"], args.model_url, tools),
        "token_measurement": "llama.cpp chat template; request_tokens includes the configured tool schemas",
    }
    if raw != log_path.read_bytes():
        raise ValueError("Source changed during preparation; take another snapshot")
    write_json(args.out, snapshot)
    print(json.dumps({"snapshot": str(args.out), "message_tokens": snapshot["message_tokens"],
                      "request_tokens": snapshot["request_tokens"],
                      "groups": len(snapshot["groups"]), "files": len(inventory)}, ensure_ascii=False))


def pack(snapshot, plan, continuation, max_chars=80000):
    if set(plan) != {"version", "summary", "keep_groups", "files"} or plan["version"] != 1:
        raise ValueError("Plan requires version=1, summary, keep_groups and files")
    summary = plan["summary"]
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 12000:
        raise ValueError("Summary must contain 1..12000 characters")
    ids = plan["keep_groups"]
    if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids) or len(ids) != len(set(ids)):
        raise ValueError("keep_groups must be a list of unique group IDs")
    lookup = {group["id"]: group for group in snapshot["groups"]}
    if set(ids) - lookup.keys():
        raise ValueError("Unknown group ID")
    # Preserve chronological order even if the model lists references out of order.
    groups = [group for group in snapshot["groups"] if group["id"] in ids]
    root = Path(snapshot["workspace"]).resolve()
    files = []
    if not isinstance(plan["files"], list):
        raise ValueError("files must be a list")
    for item in plan["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "start_line", "end_line"}:
            raise ValueError("Each file needs path, start_line and end_line")
        relative = Path(item["path"])
        target = (root / relative).resolve()
        if relative.is_absolute() or root not in target.parents:
            raise ValueError("File selection escapes the task workspace")
        start, end = item["start_line"], item["end_line"]
        if type(start) is not int or type(end) is not int or not 1 <= start <= end:
            raise ValueError("File line ranges must be positive and inclusive")
        raw = target.read_bytes()
        if len(raw) > 2_000_000:
            raise ValueError("Selected file exceeds 2 MB")
        lines = raw.decode("utf-8").splitlines(keepends=True)
        if end > len(lines):
            raise ValueError(f"Line range exceeds {item['path']}: {len(lines)} lines")
        files.append({**item, "sha256": digest(raw), "content": "".join(lines[start - 1:end])})
    context = {
        "source_session_id": snapshot["source_session_id"],
        "workspace": str(root), "user_inputs_verbatim": snapshot["users"],
        "handoff_summary": summary, "historical_groups": groups,
        "current_file_snapshots": files,
    }
    prompt = (
        "这是同一任务在新会话中的上下文交接。继续工作，不要重复已完成的阶段。\n"
        "以下 user_inputs_verbatim 是按时间排列的原始用户要求，后来的修正优先；"
        "handoff_summary 是模型生成的工作交接，可能有遗漏；historical_groups 是历史记录，"
        "current_file_snapshots 是打包时读取并冻结的文件内容，之后文件仍可能变化。\n"
        "文件片段已经在输入中提供，可以直接使用；需要其他内容或确认最新版本时再读取。\n"
        "当前请求：" + continuation + "\n\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
    )
    if len(prompt) > max_chars:
        raise ValueError(f"Handoff contains {len(prompt)} characters, limit is {max_chars}; select fewer items")
    return {
        "version": 1, "source_session_id": snapshot["source_session_id"],
        "source_seq": snapshot["source_seq"], "source_events_sha256": snapshot["source_events_sha256"],
        "model": snapshot["model"], "context": context,
        "messages": [snapshot["messages"][0], {"role": "user", "content": prompt}],
    }


def pack_command(args):
    snapshot, plan = read_json(args.snapshot), read_json(args.plan)
    bundle = pack(snapshot, plan, args.task_file.read_text(encoding="utf-8"), args.max_chars)
    bundle["source_message_tokens"] = snapshot["message_tokens"]
    bundle["source_request_tokens"] = snapshot["request_tokens"]
    bundle["message_tokens"] = count_tokens(bundle["messages"], args.model_url)
    bundle["request_tokens"] = count_tokens(bundle["messages"], args.model_url, snapshot["tools"])
    if bundle["request_tokens"] > args.max_tokens:
        raise ValueError(f"Packed messages exceed {args.max_tokens} tokens; revise the plan")
    write_json(args.out, bundle)
    print(json.dumps({"bundle": str(args.out), "before_tokens": snapshot["message_tokens"],
                      "after_tokens": bundle["message_tokens"], "request_tokens": bundle["request_tokens"],
                      "files": len(bundle["context"]["current_file_snapshots"]),
                      "groups": len(bundle["context"]["historical_groups"])}, ensure_ascii=False))


def start(args):
    bundle = read_json(args.bundle)
    sys.path.insert(0, str(args.project.resolve()))
    from agent.workflow.config import load
    config = load(args.project.resolve() / "config.yaml")
    system = config.system_prompt.replace("{workspace}", str(config.workspace.resolve()))
    if bundle["messages"][0] != {"role": "system", "content": system}:
        raise ValueError("System prompt changed since snapshot; review before starting")
    if args.out.exists():
        raise ValueError("Output already records a target session; refuse to create a duplicate")
    sid = request(args.api, "/api/sessions", {}, "POST")["id"]
    result = {"source_session_id": bundle["source_session_id"], "target_session_id": sid,
              "bundle": str(args.bundle.resolve()), "input_sha256": digest(args.bundle.read_bytes()),
              "accepted": False}
    write_json(args.out, result)
    request(args.api, f"/api/sessions/{sid}", {"title": args.title}, "PATCH")
    request(args.api, f"/api/sessions/{sid}/model", {
        "provider": bundle["model"]["provider"], "model": bundle["model"]["name"],
    }, "POST")
    request(args.api, f"/api/sessions/{sid}/messages", {"content": bundle["messages"][1]["content"]}, "POST")
    result["accepted"] = True
    write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--project", type=Path, default=Path.cwd())
    prepare_parser.add_argument("--session", required=True)
    prepare_parser.add_argument("--workspace", type=Path, required=True)
    prepare_parser.add_argument("--out", type=Path, required=True)
    pack_parser = commands.add_parser("pack")
    pack_parser.add_argument("--snapshot", type=Path, required=True)
    pack_parser.add_argument("--plan", type=Path, required=True)
    pack_parser.add_argument("--out", type=Path, required=True)
    pack_parser.add_argument("--task-file", type=Path, required=True,
                             help="User-authorized continuation, kept separate from the model summary")
    pack_parser.add_argument("--max-chars", type=int, default=80000)
    pack_parser.add_argument("--max-tokens", type=int, default=16000)
    start_parser = commands.add_parser("start")
    start_parser.add_argument("--project", type=Path, default=Path.cwd())
    start_parser.add_argument("--bundle", type=Path, required=True)
    start_parser.add_argument("--out", type=Path, required=True)
    start_parser.add_argument("--title", default="上下文整理实验 · 游戏开发续接会话")
    for sub in (prepare_parser, start_parser):
        sub.add_argument("--api", default="http://127.0.0.1:8200")
    for sub in (prepare_parser, pack_parser):
        sub.add_argument("--model-url", default="http://127.0.0.1:18080")
    args = parser.parse_args()
    {"prepare": prepare, "pack": pack_command, "start": start}[args.command](args)


if __name__ == "__main__":
    main()

"""External experiment driver; no changes to chat_ai's production execution loop."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    args = parser.parse_args()
    project, experiment = args.project.resolve(), args.experiment.resolve()
    sys.path.insert(0, str(project / "skills/context-handoff/scripts"))
    sys.path.insert(0, str(project))
    from handoff import read_json, write_json, request, count_tokens
    from agent.tools.schema import ToolCallAssembler

    info = read_json(experiment / "experiment.json")
    source = info["source_session_id"]
    api = "http://127.0.0.1:8200"
    model_url = "http://127.0.0.1:18080"
    script = project / "skills/context-handoff/scripts/handoff.py"
    skill = project / "skills/context-handoff/SKILL.md"
    threshold = info["threshold_tokens"]
    last_progress = None

    def records(sid):
        path = project / "storage/sessions" / sid / "events.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line.endswith("}")]

    def listed(sid):
        return next(item for item in request(api, "/api/sessions")["sessions"] if item["id"] == sid)

    def log(message):
        print(time.strftime("%H:%M:%S"), message, flush=True)

    def wait_idle(sid, timeout=1200):
        deadline = time.monotonic() + timeout
        seen = None
        while time.monotonic() < deadline:
            events = records(sid)
            completed = [e for e in events if e["type"] == "model.completed"]
            current = (len(completed), events[-1]["type"])
            if current != seen:
                usage = completed[-1].get("usage") if completed else {}
                log(f"session={sid[:8]} models={len(completed)} latest={current[1]} usage={usage}")
                seen = current
            if not listed(sid)["busy"]:
                return events
            time.sleep(4)
        request(api, f"/api/sessions/{sid}/control/stop", {}, "POST")
        raise TimeoutError(f"Experiment stopped its session after {timeout}s: {sid}")

    def run(*arguments):
        subprocess.run([sys.executable, str(script), *map(str, arguments)], cwd=project, check=True)

    # Trigger from real server usage, after the completed tool batch is recorded.
    deadline = time.monotonic() + 1800
    extra_turns = 0
    while time.monotonic() < deadline:
        events = records(source)
        completed = [e for e in events if e["type"] == "model.completed"]
        usage = (completed[-1].get("usage") or {}) if completed else {}
        if len(completed) != last_progress:
            log(f"source models={len(completed)} usage={usage}")
            last_progress = len(completed)
        context_tokens = usage.get("total_tokens", 0)
        latest = max((i for i, e in enumerate(events) if e["type"] == "model.completed"), default=-1)
        assembler = ToolCallAssembler()
        model_start = max((i for i, e in enumerate(events[:latest]) if e["type"] == "model.started"), default=-1)
        for event in events[model_start + 1:latest]:
            if event["type"] == "tool_call.delta":
                assembler.add(event["delta"])
        calls = {call.id for call in assembler.finish()}
        replies = set()
        for event in events[latest + 1:]:
            if event["type"] == "tool.completed":
                replies.add(event["callId"])
        busy = listed(source)["busy"]
        if context_tokens >= threshold and calls <= replies:
            info["trigger_usage"] = usage
            info["trigger_completed_models"] = len(completed)
            info["trigger_observed_seq"] = events[-1]["seq"]
            info["trigger_was_running"] = busy
            write_json(experiment / "experiment.json", info)
            if busy:
                request(api, f"/api/sessions/{source}/control/stop", {}, "POST")
                wait_idle(source, 90)
            log(f"Reached {threshold}: {context_tokens}; preparing handoff")
            break
        if not busy:
            if extra_turns >= 2:
                raise RuntimeError("Task finished below threshold after two real review turns; no artificial padding added")
            extra_turns += 1
            prompt = (
                "继续阶段2代码审查，仍暂不实现阶段3。请完整读取本任务当前引擎、界面、测试及设计文件，"
                "逐项核对全部原始规则与后续修正，修复真实问题并运行完整测试；"
                "补充能够证明存档恢复后动作确定性、迷雾可见范围和回放一致性的测试，"
                "保存简明的REVIEW.md。不要重复已经证明正确的工作，不要delegate。最后submit真实结果。"
            )
            (experiment / f"review-{extra_turns}-prompt.txt").write_text(prompt)
            request(api, f"/api/sessions/{source}/messages", {"content": prompt}, "POST")
        time.sleep(3)
    else:
        request(api, f"/api/sessions/{source}/control/stop", {}, "POST")
        raise TimeoutError("Source did not reach the experimental threshold within 30 minutes")

    snapshot_path, plan_path = experiment / "snapshot.json", experiment / "plan.json"
    bundle_path, target_path = experiment / "bundle.json", experiment / "target-session.json"
    run("prepare", "--project", project, "--session", source, "--workspace", info["game_root"], "--out", snapshot_path)
    snapshot = read_json(snapshot_path)
    manifest = {
        "source_session_id": source, "request_tokens": snapshot["request_tokens"],
        "workspace": snapshot["workspace"], "file_inventory": snapshot["file_inventory"],
        "groups": [{"id": group["id"], "preview": json.dumps(group["messages"], ensure_ascii=False)[:180]}
                   for group in snapshot["groups"]],
    }
    write_json(experiment / "manifest.json", manifest)
    prompt = (
        "现在暂停游戏开发，只整理上下文。本轮不要继续修复、实现、测试或delegate。\n"
        f"请先用read_file读取整理skill：{skill}，再读取分组与文件清单：{experiment / 'manifest.json'}。\n"
        f"完整冻结快照位于{snapshot_path}，你已有的对话记录用于理解进展；仅必要时分页读取快照。\n"
        f"按skill的JSON格式，用write_file把交接计划写入工作区相对路径"
        f"{info['game_relative']}/handoff-plan.json。摘要请准确记录当前未完成的阶段2和阶段3、"
        "用户后续修正、当前真实测试结果和已知失败，不要声称中断中的工作已经完成。\n"
        "files请选择当前最有价值的少量代码，先用run_bash的wc -l核对实际行数；"
        "总交接输入预算16K token，不要把全部历史和全部文件原样塞入。"
        "用户原始输入由脚本完整保留。写完JSON后只简短报告路径并结束本轮。"
    )
    (experiment / "compaction-prompt.txt").write_text(prompt)
    request(api, f"/api/sessions/{source}/messages", {"content": prompt}, "POST")
    wait_idle(source, 900)
    generated_plan = Path(info["game_root"]) / "handoff-plan.json"
    plan_path.write_bytes(generated_plan.read_bytes())
    continuation = (
        "继续完成《星港回收站》尚未完成的阶段2和阶段3。先简短说明从交接承接到的有效要求、"
        "未完成事项和下一步，再实际实现、运行全部测试并submit真实最终报告。"
        "开发仅限交接中的任务目录，不使用delegate。"
    )
    continue_path = experiment / "continue.txt"
    continue_path.write_text(continuation)
    run("pack", "--snapshot", snapshot_path, "--plan", plan_path, "--task-file", continue_path, "--out", bundle_path)
    run("start", "--project", project, "--bundle", bundle_path, "--out", target_path)
    target = read_json(target_path)["target_session_id"]
    info["target_session_id"] = target
    write_json(experiment / "experiment.json", info)
    events = wait_idle(target, 1500)
    bundle = read_json(bundle_path)
    original = read_json(snapshot_path)
    first_usage = next(e.get("usage") for e in events if e["type"] == "model.completed")
    result = {
        "source_session_id": source, "target_session_id": target,
        "trigger_usage": info["trigger_usage"],
        "source_request_tokens": original["request_tokens"],
        "packed_request_tokens": bundle["request_tokens"], "target_first_usage": first_usage,
        "user_inputs": len(original["users"]), "kept_groups": len(bundle["context"]["historical_groups"]),
        "file_snapshots": len(bundle["context"]["current_file_snapshots"]),
        "terminal": events[-1]["type"],
        "exact_user_inputs_preserved": original["users"] == bundle["context"]["user_inputs_verbatim"],
        "source_summary": read_json(plan_path)["summary"],
    }
    write_json(experiment / "result.json", result)
    log("Finished: " + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

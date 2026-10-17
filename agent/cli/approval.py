"""Terminal presentation and decisions; approval policy lives in tools.approval."""
import json
import time
from prompt_toolkit.patch_stdout import patch_stdout


def render_approval_event(event):
    if event["type"] == "approval.requested":
        print(f"\n待审批 {event['id']} · 会话 {event['sessionId']} · {event['tool']}")
        if event.get("workspace"):
            print(f"工作目录：{event['workspace']}")
        print(json.dumps(event["arguments"], ensure_ascii=False, indent=2))
        print("/approve <审批ID> 批准本次；/reject <审批ID> 拒绝本次；/stop <会话ID> 停止来源任务。")
    elif event["type"] == "approval.resolved":
        label = {"approved": "已批准本次", "rejected": "已拒绝本次", "cancelled": "审批已取消"}
        print(f"\n{label[event['decision']]} · {event['approvalId']}")


def handle_approval_command(text, gate, stop=None):
    parts = text.split()
    if not parts or parts[0] not in {"/access", "/approve", "/reject", "/approvals", "/stop"}:
        return False
    if parts[0] == "/approvals":
        print(json.dumps(gate.snapshot(), ensure_ascii=False, indent=2))
    elif len(parts) != 2:
        print("用法：/access audit|full_access；/approve <审批ID>；/reject <审批ID>；/stop <会话ID>")
    elif parts[0] == "/stop":
        if not stop or parts[1] not in {item["sessionId"] for item in gate.snapshot()["pending"]}:
            raise ValueError("此会话没有待审批操作")
        stop(parts[1])
    elif parts[0] == "/access":
        gate.set_mode(parts[1])
        print("访问模式：" + ("审计" if parts[1] == "audit" else "完全访问"))
    else:
        gate.resolve(parts[1], parts[0] == "/approve")
    return True


def wait_for_execution(registry, runtime, prompt_session, *, include_children=False):
    """Keep input on the main thread, including approvals from concurrent children."""
    while True:
        with registry.lock:
            active = list(registry.items.values()) if include_children else [runtime]
        if not any(item.busy for item in active):
            return
        pending = runtime.approvals.snapshot()["pending"]
        if not pending:
            time.sleep(0.05)
            continue
        item = pending[0]
        try:
            with patch_stdout():
                answer = prompt_session.prompt(f"批准本次 {item['tool']}？[y/N，Ctrl+C 停止] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            registry.get(item["sessionId"]).stop()
            continue
        try:
            runtime.approvals.resolve(item["id"], answer in {"y", "yes", "批准"})
        except ValueError:
            print("此审批已处理或已取消。")

"""Pure context policy: select history and produce a messages StateUpdate."""
from .state import AgentState, StateUpdate


def plan(state: AgentState, tokens: int, config: dict) -> dict | None:
    if not config.get("enabled", False) or tokens < config["trigger_tokens"]:
        return None
    messages = state["messages"]
    # Keep the configured system prompt, latest user input, and last complete
    # assistant/tool group. A long tool loop can still compact within one turn.
    latest_user = max((i for i, m in enumerate(messages) if m["role"] == "user"), default=-1)
    first_user = latest_user
    while first_user > 0 and messages[first_user - 1]['role'] == 'user':
        first_user -= 1
    tail_end = len(messages) - 1
    while tail_end > 0 and messages[tail_end]['role'] == 'user':
        tail_end -= 1
    tail = tail_end
    while tail > 0 and messages[tail]["role"] == "tool":
        tail -= 1
    protected = {0, *range(first_user, latest_user + 1), *range(tail, tail_end + 1)}
    history = [m for i, m in enumerate(messages) if i not in protected]
    if not history:
        raise ValueError("上下文超过整理阈值，但没有可整理的历史；请缩小当前输入或新建会话。")
    retained = [m for i, m in enumerate(messages) if i in protected and i != 0]
    return {"system": messages[:1], "history": history, "retained": retained}


def build_update(selected: dict, summary: str) -> StateUpdate:
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("上下文摘要为空，原上下文保持不变。")
    return {"messages": [*selected["system"], {
        "role": "assistant",
        "content": "[自动整理的历史摘要；可能有遗漏，以用户最新要求和实际文件为准。]\n" + summary.strip(),
    }, *selected["retained"]]}


def validate_compacted_size(before: int, after: int, config: dict) -> None:
    if after >= before:
        raise ValueError(f"整理后上下文未缩小（{after} tokens），原上下文保持不变。")
    if after >= config["trigger_tokens"]:
        raise ValueError(f"整理后上下文仍达到触发阈值（{after} tokens），原上下文保持不变。")

"""A cancellable summary request, isolated from agent tools and execution state."""
import json

from .openai_compatible import stream


def summarize_context(client, model, provider, selected, config, context):
    prompt = config["prompt_file"].read_text(encoding="utf-8")
    messages = [{"role": "system", "content": prompt}, {
        "role": "user", "content": json.dumps({
            "history_to_summarize": selected["history"],
            "retained_context": selected["retained"],
        }, ensure_ascii=False),
    }]
    parts = []
    reason = None
    for chunk in stream(client, model, messages, [], provider, context=context):
        if chunk.tool_deltas:
            raise ValueError("摘要请求不允许调用工具")
        parts.append(chunk.content)
        reason = chunk.finish_reason or reason
    context.cancellation.raise_if_cancelled()
    if reason != "stop":
        raise ValueError(f"上下文摘要未正常完成（{reason}），未保存不完整摘要。")
    return "".join(parts)

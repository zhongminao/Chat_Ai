from .messages import assistant_message
from ..tools.schema import ToolCallAssembler
from ..model.messages import build_user_message, build_tool_message


def restore_messages(events: list[dict]) -> list[dict]:
    """Rebuild model messages from session events without I/O."""
    messages = []
    text = []
    assembler = ToolCallAssembler()
    pending = set()
    model_finished = False

    def close_pending():
        for call_id in sorted(pending):
            messages.append({
                "role": "tool", "tool_call_id": call_id,
                "content": "[tool error] Previous execution did not finish.",
            })
        pending.clear()

    for event in events:
        kind = event["type"]
        if kind == "turn.started":
            close_pending()
            if messages and messages[-1]["role"] == "user":
                messages.append({
                    "role": "assistant",
                    "content": "[assistant system response] Previous request did not finish.",
                })
            images = [image["id"] for image in event.get("images", [])]
            messages.append(build_user_message(event["prompt"], images))
        elif kind == "model.started":
            text = []
            assembler = ToolCallAssembler()
            model_finished = False
        elif kind == "message.delta":
            text.append(event["text"])
        elif kind == "tool_call.delta":
            assembler.add(event["delta"])
        elif kind == "model.completed":
            model_finished = True
            calls = assembler.finish()
            message = assistant_message("".join(text), calls)
            if calls:
                pending.update(call.id for call in calls)
            messages.append(message)
        elif kind == "turn.cancelled":
            close_pending()
            content = event.get("answer") or "".join(text)
            if content and not model_finished:
                messages.append({"role": "assistant", "content": content})
        elif kind == "tool.completed":
            images = [image["id"] for image in event.get("model_images", [])]
            messages.append({**build_tool_message(event["callId"], event["result"], images), "name": event["tool"]})
            pending.discard(event["callId"])
    close_pending()
    if messages and messages[-1]["role"] == "user":
        messages.append({
            "role": "assistant",
            "content": "[assistant system response] Previous request did not finish.",
        })
    return messages

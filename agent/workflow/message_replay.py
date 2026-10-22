from .message_updates import assistant_message, mailbox_notice
from ..tools.schema import ToolCallAssembler
from ..model.request_messages import build_user_message, build_tool_message


def restore_display_messages(events: list[dict]) -> list[dict]:
    """Rebuild the full display history; compaction does not erase history."""
    return _restore(events, [])


def restore_model_messages(events: list[dict], system: dict) -> list[dict]:
    """Restore the latest persisted context, then replay only later messages."""
    for index in range(len(events) - 1, -1, -1):
        if events[index]["type"] == "context.compacted":
            saved = events[index]["messages"]
            # As before compaction, explicit config changes update the role's
            # system prompt. All persisted conversation messages stay exact.
            return _restore(events[index + 1:], [system, *saved[1:]], tool_names=False, runtime_notices=True)
    return [system, *_restore(events, [], tool_names=False, runtime_notices=True)]


def _restore(events: list[dict], initial: list[dict], *, tool_names=True, runtime_notices=False) -> list[dict]:
    messages = list(initial)
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
        if kind == 'guidance.applied':
            messages.append(build_user_message(event['content'], [i['id'] for i in event.get('images', [])]))
        elif kind == 'mailbox.notified' and runtime_notices:
            messages.append(mailbox_notice(event['messageIds']))
        elif kind == "turn.started":
            close_pending()
            text = []
            model_finished = False
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
        elif kind == "completion.reminded":
            messages.append({"role": "system", "content": event["content"]})
        elif kind == "turn.cancelled":
            close_pending()
            content = event.get("answer") or "".join(text)
            if content and not model_finished:
                messages.append({"role": "assistant", "content": content})
        elif kind == "tool.completed":
            images = [image["id"] for image in event.get("model_images", [])]
            message = build_tool_message(event["callId"], event["result"], images)
            messages.append({**message, "name": event["tool"]} if tool_names else message)
            pending.discard(event["callId"])
    close_pending()
    return messages

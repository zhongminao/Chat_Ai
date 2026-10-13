#!/usr/bin/env python3
"""Project one session's events.jsonl into conversation.jsonl.

Usage:
    python project_conversation.py /path/to/storage/sessions/<session_id>
"""

import argparse
import json
from pathlib import Path


def project(session_dir: Path) -> Path:
    events_path = session_dir / "events.jsonl"
    conversation_path = session_dir / "conversation.jsonl"
    messages: list[dict] = []

    if not events_path.exists():
        raise FileNotFoundError(events_path)

    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        event = json.loads(line)
        event_type = event.get("type")

        if event_type == "turn.started":
            messages.append({
                "runId": event.get("runId"),
                "role": "user",
                "content": event.get("prompt", ""),
            })
        elif event_type == "tool.completed":
            messages.append({
                "runId": event.get("runId"),
                "role": "tool",
                "name": event.get("tool", ""),
                "content": event.get("result", ""),
            })
        elif event_type == "turn.completed":
            messages.append({
                "runId": event.get("runId"),
                "role": "assistant",
                "content": event.get("answer", ""),
            })

    temp_path = conversation_path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        for message in messages:
            file.write(json.dumps(message, ensure_ascii=False) + "\n")
    temp_path.replace(conversation_path)
    return conversation_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", type=Path)
    args = parser.parse_args()
    path = project(args.session_dir.expanduser().resolve())
    print(path)


if __name__ == "__main__":
    main()

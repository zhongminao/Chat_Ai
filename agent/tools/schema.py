import json
from dataclasses import dataclass
from typing import Any


DELEGATE_SCHEMA = {"type": "function", "function": {
    "name": "delegate",
    "description": "Start an independent child task and return its session_id immediately. The child has its own history, configured system prompt and shared workspace, but cannot delegate. It keeps running after your reply ends. Results require watch and reading result_path.",
    "parameters": {"type": "object", "properties": {
        "user_prompt": {"type": "string", "description": "Complete task, scope, permissions, context, paths, acceptance criteria and deliverables."}},
        "required": ["user_prompt"], "additionalProperties": False}}}


NOTIFY_SCHEMA = {"type": "function", "function": {
    "name": "notify_agent",
    "description": "Send durable private task-tree mail: parent to active children, children to parent or siblings. Delivery fails when a child is submitting or finished. Mail IDs are notified automatically; bodies require read_agent_message. Mail does not wake an idle agent.",
    "parameters": {"type": "object", "properties": {
        "to": {"type": "string", "description": "Recipient session_id; child agents may use parent"},
        "content": {"type": "string", "description": "Message body"},
        "cc": {"type": "array", "items": {"type": "string"}, "description": "Optional sibling session_ids for child feedback"},
        "kind": {"type": "string", "enum": ["notification", "feedback"]}},
        "required": ["to", "content"], "additionalProperties": False}}}

INBOX_SCHEMA = {"type": "function", "function": {
    "name": "agent_inbox",
    "description": "List received task-tree mail without marking it read. unread_only filters unacknowledged mail. Use read_agent_message for bodies; automatic ID notifications make polling unnecessary.",
    "parameters": {"type": "object", "properties": {
        "unread_only": {"type": "boolean", "default": False}}, "additionalProperties": False}}}

READ_MAIL_SCHEMA = {"type": "function", "function": {
    "name": "read_agent_message",
    "description": "Read and acknowledge one received task-tree message by message_id.",
    "parameters": {"type": "object", "properties": {
        "message_id": {"type": "string"}}, "required": ["message_id"], "additionalProperties": False}}}


WATCH_SCHEMA = {"type": "function", "function": {
    "name": "watch",
    "description": "Query background tasks and mailbox state, or wait for changes. Without cursor, return a full snapshot immediately. Reuse the latest returned cursor across all resources; it is not a task ID. Changed entries contain current state, not event history. Timeouts return no changes and keep the cursor. For completed tasks read result_path; for failed/cancelled tasks inspect error and read events_path to review work already performed before deciding how to proceed. Do not poll for mail or wait when no relevant task remains.",
    "parameters": {"type": "object", "properties": {
        "cursor": {"type": ["integer", "null"], "minimum": 0,
                   "description": "Latest watch cursor; omit/null for a full snapshot."},
        "timeout": {"type": "number", "minimum": 0, "maximum": 86400, "default": 0,
                    "description": "Seconds to wait with cursor, up to 86400 (1 day). Returns early on changes; ignored without cursor."}},
        "additionalProperties": False}}}


SUBMIT_SCHEMA = {"type": "function", "function": {
    "name": "submit",
    "description": "Submit the complete Markdown final report and end execution. Call alone. If rejected for pending input, process it and retry. Children must submit successfully to finish; main agents follow their system prompt.",
    "parameters": {"type": "object", "properties": {
        "content": {"type": "string", "description": "Self-contained final report; preserve exact image URLs and local paths."}},
        "required": ["content"], "additionalProperties": False}}}


TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "read_image",
        "description": "Inspect an existing PNG/JPEG/WebP with model vision; does not publish it. Requires a vision-capable model.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Exact workspace-relative or absolute file path. Reuse saved paths; image labels and IDs are not paths."}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "show_image",
        "description": "Publish an existing PNG/JPEG/WebP and return its Markdown reference. Does not generate or render images; render HTML first.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Exact existing file path; reuse the saved path from read_image when publishing that image."}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a UTF-8 text file page by page. Absolute paths are allowed.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
            "limit": {"type": "integer", "minimum": 1, "default": 12000}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Write UTF-8 text to a file.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "edit_file",
        "description": "Replace one exact text fragment in a file.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "old": {"type": "string"},
            "new": {"type": "string"}},
            "required": ["path", "old", "new"]}}},
    {"type": "function", "function": {
        "name": "run_bash",
        "description": "Run a bash command in the workspace.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]}}},
]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


class ToolCallAssembler:
    def __init__(self):
        self.calls: dict[int, dict[str, str]] = {}

    def add(self, delta: dict[str, Any]) -> None:
        index = int(delta.get("index", 0))
        call = self.calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
        call_id = str(delta.get("id") or "")
        # Some providers repeat the complete ID instead of sending only fragments.
        if call_id != call["id"]:
            call["id"] += call_id
        function = delta.get("function") or {}
        call["name"] += str(function.get("name") or "")
        call["arguments"] += str(function.get("arguments") or "")

    def finish(self) -> list[ToolCall]:
        result = []
        for index in sorted(self.calls):
            raw = self.calls[index]
            result.append(ToolCall(
                id=raw["id"] or f"call_{index}",
                name=raw["name"],
                arguments=json.loads(raw["arguments"] or "{}"),
            ))
        return result

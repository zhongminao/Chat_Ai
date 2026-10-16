import json
from dataclasses import dataclass
from typing import Any


DELEGATE_SCHEMA = {"type": "function", "function": {
    "name": "delegate",
    "description": "Start an independent child task asynchronously and return its session_id immediately. Provide only user_prompt: the framework supplies the child's system instructions. The child receives this task, its own history and the shared workspace, and must submit a final report. It keeps running after your reply ends or is stopped. To check progress call watch() for all monitored resources, then reuse the latest watch cursor to wait. Results are not automatically injected into your conversation.",
    "parameters": {"type": "object", "properties": {
        "user_prompt": {"type": "string", "description": "Complete task, role if useful, necessary context, exact paths and expected deliverables."}},
        "required": ["user_prompt"], "additionalProperties": False}}}


WATCH_SCHEMA = {"type": "function", "function": {
    "name": "watch",
    "description": "Query all registered background resources in this main session, across resource kinds. watch() immediately returns a full snapshot. One cursor covers the entire monitor, not one agent. watch(cursor=<latest returned cursor>, timeout=60) returns resources changed since that version, waiting for any change if needed. Always reuse the latest returned cursor; timeouts return empty changes and leave it unchanged. Each changed resource contains its latest state, not a full event history. Querying does not consume results; other readers keep independent cursors. For completed agents read result_path using read_file. For failed/cancelled agents inspect error before deciding what to do. Returns references/status, not report contents.",
    "parameters": {"type": "object", "properties": {
        "cursor": {"type": ["integer", "null"], "minimum": 0,
                   "description": "The exact cursor from your latest watch result: a version of this main session's entire monitor, never an agent index or session ID. Omit/null for a full snapshot."},
        "timeout": {"type": "number", "minimum": 0, "maximum": 120, "default": 0,
                    "description": "Maximum seconds to wait for any resource change when cursor is provided. Without cursor, the snapshot returns immediately."}},
        "additionalProperties": False}}}


SUBMIT_SCHEMA = {"type": "function", "function": {
    "name": "submit",
    "description": "Submit the complete Markdown final report and end this execution. Call alone. Main agents follow their system instructions to decide when to use it; child agents must call it exactly once on completion.",
    "parameters": {"type": "object", "properties": {
        "content": {"type": "string", "description": "The complete final report in Markdown. Include exact image URLs from show_image or child reports when displaying images."}},
        "required": ["content"], "additionalProperties": False}}}


TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "read_image",
        "description": "Inspect an existing PNG, JPEG or WebP image using the current model's vision. Use this to examine a plot or screenshot before deciding what to change. Requires a vision-capable model; does not publish a preview to the user.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Exact file path, workspace-relative or absolute. Use the full saved session path supplied with an existing image. Image names, numbers and IDs are not paths; do not invent directories."}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "show_image",
        "description": "Publish an existing PNG, JPEG or WebP file as a conversation image and return its saved path. After generating a plot or screenshot, call this tool with the file path. It does not generate images.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Exact file path, workspace-relative or absolute. Reuse the full saved session path returned by read_image to display that same image. Do not use a name, number or ID as a path."},
            "name": {"type": "string", "description": "Optional display name; defaults to the original filename for new images. Names may repeat and are not image references. Setting a name for an existing image renames it."}},
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
        call["id"] += str(delta.get("id") or "")
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

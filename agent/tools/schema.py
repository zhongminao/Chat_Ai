import json
from dataclasses import dataclass
from typing import Any


DELEGATE_SCHEMA = {"type": "function", "function": {
    "name": "delegate",
    "description": "Start an independent child session asynchronously. Returns its session_id immediately. It is registered with watch. Call watch() for a snapshot, then watch(cursor=..., timeout=60) to wait for changes. Read result_path with read_file when completed. No automatic reply or result injection occurs. The child gets only these prompts, its own history and the shared workspace. Stopping your reply does not stop it.",
    "parameters": {"type": "object", "properties": {
        "system_prompt": {"type": "string", "description": "Child role and task-specific instructions."},
        "user_prompt": {"type": "string", "description": "Complete task and all necessary context, including exact paths."}},
        "required": ["system_prompt", "user_prompt"], "additionalProperties": False}}}


WATCH_SCHEMA = {"type": "function", "function": {
    "name": "watch",
    "description": "Query monitored background resources. Without cursor returns a snapshot. With cursor returns changed resources only; timeout>0 waits for any change. Use the cursor from the last watch result, not from a spawn call. A completed agent gives result_path: read that file using read_file, then decide to continue, wait again or submit. Returns status/references, not report contents. Querying does not consume results. Other resource kinds may be monitored later.",
    "parameters": {"type": "object", "properties": {
        "cursor": {"type": ["integer", "null"], "minimum": 0},
        "timeout": {"type": "number", "minimum": 0, "maximum": 120, "default": 0}},
        "additionalProperties": False}}}


SUBMIT_SCHEMA = {"type": "function", "function": {
    "name": "submit",
    "description": "Submit the final report and end this execution. Call alone, after all work is done. Required for a child task; optional for a main agent's formal deliverable. Ordinary main-agent conversation does not need submit.",
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

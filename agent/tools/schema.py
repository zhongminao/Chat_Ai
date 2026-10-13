import json
from dataclasses import dataclass
from typing import Any


DELEGATE_SCHEMA = {"type": "function", "function": {
    "name": "delegate",
    "description": "Delegate a focused task to a child agent.",
    "parameters": {"type": "object", "properties": {
        "agent": {"type": "string", "description": "Child agent name."},
        "task": {"type": "string", "description": "Focused task for the child agent."}},
        "required": ["agent", "task"]}}}


TOOL_SCHEMAS = [
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

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


ENABLE_MCP_SCHEMA = {"type": "function", "function": {
    "name": "enable_mcp",
    "description": "Connect a user-requested HTTP(S) MCP endpoint, discover its tools, and enable them for the next model request in this conversation. Call when the user explicitly requests this URL, or when a locally installed Skill invoked for the user task returns its own loopback MCP URL after starting its service. Discovering a Skill alone does not authorize arbitrary remote endpoints. Configured MCP servers already load automatically; no config entry is needed here.",
    "parameters": {"type": "object", "properties": {
        "url": {"type": "string", "description": "Full HTTP(S) MCP endpoint supplied by the user or returned by the authorized local Skill startup script."}},
        "required": ["url"], "additionalProperties": False}}}


WATCH_SCHEMA = {"type": "function", "function": {
    "name": "watch",
    "description": "Query background tasks and mailbox state, or wait for changes. Without cursor, return a full snapshot immediately. Reuse the latest returned cursor across all resources; it is not a task ID. Changed entries contain current state, not event history. User guidance wakes a waiting watch without cancelling the turn; interrupted_by_guidance indicates pending input that is delivered after the tool batch. Timeouts return no changes and keep the cursor. For completed tasks read result_path; for failed/cancelled tasks inspect error and read events_path to review work already performed before deciding how to proceed. Do not poll for mail or wait when no relevant task remains.",
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


SEARCH_SCHEMA = {"type": "function", "function": {
    "name": "search_resources",
    "description": ("仅在认为有必要时搜索本地资源，例如用户指引查找，或缺少任务所需资源、脚本、说明。已有上下文足够时直接继续，不重复检索。当前仅有少量 Skill，尚无知识库。用任务关键词查询，"
                    "无需预先知道 Skill 名称。返回匹配依据、相关原文摘录及完整说明定位；"
                    "选用 Skill 后读取完整说明再执行，不能用摘录代替规则。本工具只检索，不运行脚本或连接服务。"),
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "用户需求、文件类型或所需能力的关键词；可以直接使用用户原话。"},
        "resource_type": {"type": "string", "enum": ["skill", "knowledge"], "default": "skill",
                          "description": "Resource scope. Omit it to search skills."},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}
    }, "required": ["query"], "additionalProperties": False}}}


TOOL_SCHEMAS = [SEARCH_SCHEMA,
    {"type": "function", "function": {
        "name": "read_image",
        "description": "Read an existing local PNG/JPEG/WebP image with model vision and save it in the session. Returns session_path and a Markdown image reference. To show the image to the user, copy the returned Markdown into your reply or report; omit it when only inspecting. Do not use local file paths as image links or invent URLs. Input must be a local filesystem path, not Markdown or an /api image URL.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Exact local filesystem path to the image. Image labels, IDs, Markdown references, and API URLs are not paths."}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a UTF-8 file by line (1-based offset). Shows total lines, shown range and next offset. Lines longer than the configured maximum are abbreviated. Absolute paths are allowed.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer", "minimum": 1, "default": 1},
            "limit": {"type": "integer", "minimum": 1, "default": 50}},
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
        "name": "bash",
        "description": "Run a bash command in the workspace. Timeout is in seconds (default 30, max 86400); cancellation still stops the process.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "minimum": 1, "maximum": 86400, "default": 30,
                        "description": "Maximum execution time in seconds (up to 1 day)."}},
            "required": ["command"]}}},
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

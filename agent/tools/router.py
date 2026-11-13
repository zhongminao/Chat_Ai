import hashlib
import json
from copy import deepcopy
from urllib.parse import urlsplit
from typing import Any

from ..core.cancellation import ExecutionContext, RunCancelled
from ..storage.images import ImageStore
from .executor import execute
from .images import read_image
from .result import ToolResult
from .mcp.client import McpClient
from .mcp.results import convert_result
from .schema import DELEGATE_SCHEMA, WATCH_SCHEMA, NOTIFY_SCHEMA, INBOX_SCHEMA, READ_MAIL_SCHEMA, ENABLE_MCP_SCHEMA, TOOL_SCHEMAS
from .search import search_resources
from .search_output import DEFAULT_CONTEXT_CHARS, resource_search_output, web_search_output
from . import mailbox


class ToolRouter:
    def __init__(self, workspace, mcp: McpClient | None = None, delegate=None, watch=None, images: ImageStore | None = None, approval=None, registry=None, session_id=None, read_file_config=None, web_search_config=None):
        self.workspace = workspace
        self.read_file_config = read_file_config or {}
        self.web_search_config = web_search_config or {}
        self.registry = registry
        self.session_id = session_id
        self.approval = approval
        self.mcp = mcp
        self.delegate = delegate
        self.watch = watch
        self.submit = None
        self.images = images
        self.vision = False
        self.schemas = deepcopy(TOOL_SCHEMAS + (mcp.schemas if mcp else []))
        for schema in self.schemas:
            if schema["function"]["name"] == "read_file":
                schema["function"]["parameters"]["properties"]["limit"]["default"] = self.read_file_config.get("limit", 50)
            fn = schema["function"]
            if mcp and mcp.tools.get(fn["name"]) == ("web", "search"):
                fn["description"] = (
                    "搜索网页。默认 SearXNG；enhanced=true 使用付费 DeepSeek Search 并请求正文。"
                    "两种模式均获取最多 50 条并完整落盘；limit 只控制前多少条展示详细摘录，"
                    "剩余条目给出无模型的相关原文短句简览。预览仍受总字符预算限制。"
                )
                limit_schema = fn.get("parameters", {}).get("properties", {}).get("limit")
                if limit_schema is not None:
                    limit_schema["description"] = "详细展示条数；其余返回短句简览，不裁掉落盘结果。"
        self.pending_tools: dict[str, tuple[str, dict, list[dict]]] = {}
        self.schemas.append(ENABLE_MCP_SCHEMA)
        if delegate:
            self.schemas.append(DELEGATE_SCHEMA)
        if watch:
            self.schemas.append(WATCH_SCHEMA)
        if registry is not None and session_id:
            self.schemas.extend([NOTIFY_SCHEMA, INBOX_SCHEMA, READ_MAIL_SCHEMA])

    def commit_pending_tools(self) -> list[tuple[str, str]]:
        if not self.pending_tools:
            return []
        enabled = []
        for alias, (url, tools, schemas) in self.pending_tools.items():
            self.mcp.servers[alias] = url
            self.mcp.tools.update(tools)
            self.schemas.extend(schemas)
            enabled.append((alias, url))
        self.pending_tools.clear()
        return enabled

    def enable_mcp(self, url: str) -> str:
        if not isinstance(url, str):
            raise ValueError("MCP URL must be a string")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("MCP URL must be an HTTP(S) endpoint")
        if self.mcp is None:
            self.mcp = McpClient({})
        alias = "dynamic_" + hashlib.sha256(url.encode()).hexdigest()[:12]
        if alias in self.mcp.servers:
            if self.mcp.servers[alias] != url:
                raise ValueError("MCP alias collision")
            if alias in (server for server, _ in self.mcp.tools.values()):
                return f"MCP service already enabled: {alias}"
        if alias in self.pending_tools:
            return "MCP service already pending"
        tools, schemas = self.mcp.discover_url(url, alias)
        if not tools:
            raise ValueError("MCP service returned no tools")
        self.pending_tools[alias] = (url, tools, schemas)
        return f"MCP service discovered: {alias}; {len(tools)} tools available on next model request"

    def call(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ExecutionContext | None = None,
        *, run_id: str | None = None, call_id: str | None = None,
    ) -> str | ToolResult:
        if not any(schema["function"]["name"] == name for schema in self.schemas):
            return f"[tool error] 当前工具不可用：{name}"
        arguments = deepcopy(arguments)
        decision = "approved"
        if self.approval and name not in {"notify_agent", "agent_inbox", "read_agent_message"}:
            decision = self.approval(name, arguments, context, run_id=run_id, call_id=call_id,
                                     is_mcp=bool(self.mcp and name in self.mcp.tools))
            if not decision:
                return "[tool denied] 用户拒绝本次操作；此工具未执行。请尊重该决定，不要换用其他工具执行同一操作。"
        if context:
            context.cancellation.raise_if_cancelled()
        is_mcp = bool(self.mcp and name in self.mcp.tools)
        try:
            if name in {"notify_agent", "agent_inbox", "read_agent_message"}:
                if not self.registry or not self.session_id:
                    raise ValueError("agent mailbox is unavailable")
                if name == "notify_agent":
                    value = mailbox.send(self.registry, self.session_id, **arguments)
                elif name == "agent_inbox":
                    value = mailbox.inbox(self.registry, self.session_id, **arguments)
                else:
                    value = mailbox.read(self.registry, self.session_id, **arguments)
                return json.dumps(value, ensure_ascii=False)
            if name == "read_image":
                if self.images is None:
                    raise ValueError("session image store is unavailable")
                if not self.vision:
                    raise ValueError("当前模型未声明支持视觉，请切换到支持视觉的模型")
                return read_image(self.workspace, self.images, context=context, **arguments)
            if name == "enable_mcp":
                return self.enable_mcp(**arguments)
            if name == "search_resources":
                return resource_search_output(search_resources(self.workspace, **arguments), arguments["query"])
            if name in {"delegate", "watch", "submit"}:
                handler = getattr(self, name)
                if handler is None:
                    raise ValueError(f"{name} is unavailable")
                if name == "watch":
                    return json.dumps(handler(context=context, **arguments), ensure_ascii=False)
                return handler(context=context, **arguments) if name == "submit" else handler(**arguments)
            if is_mcp:
                web_search = self.mcp.tools[name] == ("web", "search")
                detail_limit = arguments.get("limit", 5) if web_search else None
                remote_arguments = arguments
                if web_search:
                    if type(detail_limit) is not int or not 1 <= detail_limit <= 50:
                        raise ValueError("网页搜索 limit 必须为 1–50 的整数（详细展示条数）")
                    remote_arguments = {**arguments, "limit": 50}
                result = self.mcp.call(name, remote_arguments, context)
                output = convert_result(result, self.images, vision=self.vision)
                # Adapt the configured web search only, not unrelated MCP JSON/images.
                if (web_search and not result.is_error
                        and isinstance(output, str)):
                    return web_search_output(
                        output, arguments.get("query", ""),
                        context_chars=self.web_search_config.get("context_chars", DEFAULT_CONTEXT_CHARS),
                        detail_limit=detail_limit,
                    )
                return output
            return execute(self.workspace, name, arguments, context, read_file_config=self.read_file_config,
                           allow_external_write=(name == "write_file" and decision == "full_access"))
        except RunCancelled:
            raise
        except Exception as exc:
            return f"[{'mcp' if is_mcp else 'tool'} error] {type(exc).__name__}: {exc}"

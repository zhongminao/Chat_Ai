import json
from copy import deepcopy
from typing import Any

from ..core.cancellation import ExecutionContext, RunCancelled
from ..storage.images import ImageStore
from .executor import execute
from .images import read_image, show_image
from .result import ToolResult
from .mcp.client import McpClient
from .mcp.results import convert_result
from .schema import DELEGATE_SCHEMA, WATCH_SCHEMA, NOTIFY_SCHEMA, INBOX_SCHEMA, READ_MAIL_SCHEMA, TOOL_SCHEMAS
from . import mailbox


class ToolRouter:
    def __init__(self, workspace, mcp: McpClient | None = None, delegate=None, watch=None, images: ImageStore | None = None, approval=None, registry=None, session_id=None):
        self.workspace = workspace
        self.registry = registry
        self.session_id = session_id
        self.approval = approval
        self.mcp = mcp
        self.delegate = delegate
        self.watch = watch
        self.submit = None
        self.images = images
        self.vision = False
        self.image_limit: int | None = None
        self.model_images: set[str] = set()
        self.schemas = TOOL_SCHEMAS + (mcp.schemas if mcp else [])
        if delegate:
            self.schemas.append(DELEGATE_SCHEMA)
        if watch:
            self.schemas.append(WATCH_SCHEMA)
        if registry is not None and session_id:
            self.schemas.extend([NOTIFY_SCHEMA, INBOX_SCHEMA, READ_MAIL_SCHEMA])

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
        if (self.approval and name not in {"notify_agent", "agent_inbox", "read_agent_message"}
                and not self.approval(name, arguments, context, run_id=run_id, call_id=call_id,
                                      is_mcp=bool(self.mcp and name in self.mcp.tools))):
            return "[tool denied] 用户拒绝本次操作；此工具未执行。请尊重该决定，不要换用其他工具执行同一操作。"
        if context:
            context.cancellation.raise_if_cancelled()
        if name in {"notify_agent", "agent_inbox", "read_agent_message"}:
            try:
                if not self.registry or not self.session_id:
                    raise ValueError("agent mailbox is unavailable")
                if name == "notify_agent":
                    value = mailbox.send(self.registry, self.session_id, **arguments)
                elif name == "agent_inbox":
                    value = mailbox.inbox(self.registry, self.session_id, **arguments)
                else:
                    value = mailbox.read(self.registry, self.session_id, **arguments)
                return json.dumps(value, ensure_ascii=False)
            except RunCancelled:
                raise
            except Exception as exc:
                return f"[tool error] {type(exc).__name__}: {exc}"
        if name in {"show_image", "read_image"}:
            try:
                if self.images is None:
                    raise ValueError("session image store is unavailable")
                if name == "read_image":
                    if not self.vision:
                        raise ValueError("当前模型未声明支持视觉，请切换到支持视觉的模型")
                    return read_image(self.workspace, self.images, context=context,
                                      known_images=self.model_images, max_images=self.image_limit, **arguments)
                return show_image(self.workspace, self.images, context=context, **arguments)
            except RunCancelled:
                raise
            except Exception as exc:
                return f"[tool error] {type(exc).__name__}: {exc}"
        if name in {"delegate", "watch", "submit"}:
            try:
                handler = getattr(self, name)
                if handler is None:
                    raise ValueError(f"{name} is unavailable")
                if name == "watch":
                    return json.dumps(handler(context=context, **arguments), ensure_ascii=False)
                return handler(context=context, **arguments) if name == "submit" else handler(**arguments)
            except RunCancelled:
                raise
            except Exception as exc:
                return f"[tool error] {type(exc).__name__}: {exc}"
        if self.mcp and name in self.mcp.tools:
            try:
                result = self.mcp.call(name, arguments, context)
                return convert_result(result, self.images, vision=self.vision,
                                      known_images=self.model_images, max_images=self.image_limit)
            except RunCancelled:
                raise
            except Exception as exc:
                return f"[mcp error] {type(exc).__name__}: {exc}"
        return execute(self.workspace, name, arguments, context)

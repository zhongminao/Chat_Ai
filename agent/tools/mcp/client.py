import asyncio
import json
import threading
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from ...core.cancellation import ExecutionContext, RunCancelled


class McpRuntime:
    def __init__(self, servers: dict[str, str]):
        self.servers = dict(servers)
        self.tools: dict[str, tuple[str, str]] = {}
        self.schemas: list[dict[str, Any]] = []
        for name, url in self.servers.items():
            for tool in self._list(url):
                tool_name = f"mcp_{name}_{tool.name}"
                self.tools[tool_name] = (name, tool.name)
                self.schemas.append({
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": tool.description or "",
                        "parameters": tool.input_schema,
                    },
                })

    def _list(self, url: str):
        async def request():
            async with streamable_http_client(url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return (await session.list_tools()).tools
        return asyncio.run(request())

    def call(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ExecutionContext | None = None,
    ) -> str:
        server, tool = self.tools[name]
        url = self.servers[server]
        loop = asyncio.new_event_loop()
        result: dict[str, Any] = {}
        failure: list[BaseException] = []
        completed = threading.Event()
        task_box: dict[str, asyncio.Task] = {}

        def cancel_task() -> None:
            def cancel() -> None:
                task = task_box.get("task")
                if task:
                    task.cancel()
            try:
                loop.call_soon_threadsafe(cancel)
            except RuntimeError:
                pass

        def run() -> None:
            asyncio.set_event_loop(loop)
            try:
                task_box["task"] = loop.create_task(
                    self._call(url, tool, arguments, context)
                )
                result["value"] = loop.run_until_complete(task_box["task"])
            except BaseException as exc:
                failure.append(exc)
            finally:
                completed.set()
                loop.close()

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        remove_callback = (
            context.cancellation.add_callback(cancel_task)
            if context else lambda: None
        )
        try:
            while not completed.wait(0.1):
                if context:
                    context.cancellation.raise_if_cancelled()
            if context:
                context.cancellation.raise_if_cancelled()
            if failure:
                raise failure[0]
            value = result["value"]
            if value.is_error:
                return "[mcp error] " + self._content(value)
            structured = value.structured_content
            return json.dumps(structured, ensure_ascii=False) if structured is not None else self._content(value)
        except RunCancelled:
            raise
        finally:
            remove_callback()

    @staticmethod
    async def _call(url: str, tool: str, arguments: dict[str, Any], context: ExecutionContext | None):
        if context:
            context.cancellation.raise_if_cancelled()
        async with streamable_http_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments)
                if context:
                    context.cancellation.raise_if_cancelled()
                return result

    @staticmethod
    def _content(result) -> str:
        return "\n".join(
            item.text for item in result.content if getattr(item, "text", None)
        )

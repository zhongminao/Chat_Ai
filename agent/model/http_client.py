"""Cancellable async HTTP requests behind the synchronous model stream interface."""
import asyncio
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from openai import AsyncOpenAI

from ..core.cancellation import ExecutionContext


class ModelHttpClient:
    def __init__(self, **options):
        self.client = AsyncOpenAI(**options)
        self.loop = asyncio.new_event_loop()

    def _wait(self, operation, context: ExecutionContext | None):
        task = asyncio.ensure_future(operation, loop=self.loop)
        remove = (context.cancellation.add_callback(
            lambda: self.loop.call_soon_threadsafe(task.cancel)
        ) if context else lambda: None)
        try:
            return self.loop.run_until_complete(task)
        except (asyncio.CancelledError, Exception):
            if context:
                context.cancellation.raise_if_cancelled()
            raise
        finally:
            remove()

    def stream(self, options: dict, context: ExecutionContext | None = None):
        if context:
            context.cancellation.raise_if_cancelled()
        response = None
        try:
            response = self._wait(self.client.chat.completions.create(**options), context)
            iterator = response.__aiter__()
            while True:
                if context:
                    context.cancellation.raise_if_cancelled()
                try:
                    raw = self._wait(anext(iterator), context)
                except StopAsyncIteration:
                    break
                if context:
                    context.cancellation.raise_if_cancelled()
                yield raw
        finally:
            if response is not None:
                self.loop.run_until_complete(response.close())

    def post_json(self, path: str, body: dict, context: ExecutionContext | None = None):
        """Cancellable provider auxiliary request, using the same HTTP resources."""
        if context:
            context.cancellation.raise_if_cancelled()
        base = urlsplit(str(self.client.base_url))
        url = urlunsplit((base.scheme, base.netloc, base.path.rstrip("/").removesuffix("/v1") + path, "", ""))

        return self._wait(self.client.post(url, cast_to=dict[str, Any], body=body), context)

    def close(self):
        if not self.loop.is_closed():
            try:
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                self.loop.run_until_complete(self.client.close())
            finally:
                self.loop.close()

"""Cancellable async HTTP requests behind the synchronous model stream interface."""
import asyncio

from openai import AsyncOpenAI

from ..core.cancellation import ExecutionContext


class ModelRequest:
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

    def close(self):
        if not self.loop.is_closed():
            try:
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                self.loop.run_until_complete(self.client.close())
            finally:
                self.loop.close()

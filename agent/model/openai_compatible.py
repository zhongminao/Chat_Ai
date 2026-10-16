from collections.abc import Iterator
from contextlib import closing
from typing import Any, Protocol

from ..core.cancellation import ExecutionContext
from .protocol import ModelChunk, ToolCallDelta
from .messages import request_messages
from ..storage.images import ImageStore


class ProviderAdapter(Protocol):
    def request_options(self) -> dict[str, Any]:
        ...

    def parse_chunk(self, raw: Any) -> ModelChunk:
        ...


def parse_chunk(raw: Any, reasoning_field: str = "reasoning_content") -> ModelChunk:
    usage = None
    if getattr(raw, "usage", None):
        usage = raw.usage.model_dump()

    if not raw.choices:
        return ModelChunk(usage=usage)

    choice = raw.choices[0]
    delta = choice.delta
    tool_deltas = []
    for item in getattr(delta, "tool_calls", None) or []:
        function = getattr(item, "function", None)
        tool_deltas.append(
            ToolCallDelta(
                index=getattr(item, "index", 0),
                id=getattr(item, "id", "") or "",
                name=getattr(function, "name", "") or "",
                arguments=getattr(function, "arguments", "") or "",
            )
        )

    return ModelChunk(
        content=getattr(delta, "content", None) or "",
        reasoning=getattr(delta, reasoning_field, None) or "",
        tool_deltas=tuple(tool_deltas),
        finish_reason=choice.finish_reason,
        usage=usage,
    )


def stream(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    provider: ProviderAdapter,
    context: ExecutionContext | None = None,
    images: ImageStore | None = None,
    read_images: bool = True,
) -> Iterator[ModelChunk]:
    options = {
        "model": model,
        "messages": request_messages(messages, images, read_images=read_images),
        "tools": tools,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    options.update(provider.request_options())

    with closing(client.stream(options, context)) as response:
        for raw in response:
            yield provider.parse_chunk(raw)

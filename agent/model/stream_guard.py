"""Bound runaway model tool-call streams before recording their deltas."""


class ModelStreamGuard:
    # Per model request, not per tool execution. Long-running tools/watch are unaffected.
    MAX_TOOL_DELTAS = 4096
    MAX_TOOL_BYTES = 512 * 1024
    MAX_SINGLE_DELTA_BYTES = 64 * 1024

    def __init__(self):
        self.tool_deltas = 0
        self.tool_bytes = 0

    def check(self, delta) -> None:
        size = sum(len(value.encode('utf-8')) for value in
                   (delta.id, delta.name, delta.arguments))
        self.tool_deltas += 1
        self.tool_bytes += size
        if (size > self.MAX_SINGLE_DELTA_BYTES or
                self.tool_deltas > self.MAX_TOOL_DELTAS or
                self.tool_bytes > self.MAX_TOOL_BYTES):
            raise RuntimeError(
                'Model tool-call stream exceeded safety budget '
                f'(deltas={self.tool_deltas}, bytes={self.tool_bytes}); '
                'possible malformed or runaway provider response.'
            )

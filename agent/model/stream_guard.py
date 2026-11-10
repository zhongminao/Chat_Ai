"""Bound tool argument generation before assembling, logging or executing it."""
from dataclasses import dataclass


@dataclass
class _ArgumentProgress:
    in_string: bool = False
    escaped: bool = False
    whitespace: int = 0
    empty_deltas: int = 0


class ModelStreamGuard:
    # Byte/count budgets cover one model request; progress is tracked per call index.
    MAX_TOOL_DELTAS = 64 * 1024
    MAX_TOOL_BYTES = 512 * 1024
    MAX_SINGLE_DELTA_BYTES = 64 * 1024
    MAX_EMPTY_DELTAS = 256
    MAX_JSON_WHITESPACE = 1024

    def __init__(self):
        self.tool_deltas = 0
        self.tool_bytes = 0
        self.calls: dict[int, _ArgumentProgress] = {}

    def _reject(self, delta, reason):
        raise RuntimeError(
            f'Model tool-call argument generation rejected: {reason} '
            f'(index={delta.index}, deltas={self.tool_deltas}, bytes={self.tool_bytes}); '
            'the incomplete tool call was not executed.'
        )

    def check(self, delta) -> None:
        size = sum(len(value.encode('utf-8')) for value in
                   (delta.id, delta.name, delta.arguments))
        self.tool_deltas += 1
        self.tool_bytes += size
        if (size > self.MAX_SINGLE_DELTA_BYTES or
                self.tool_deltas > self.MAX_TOOL_DELTAS or
                self.tool_bytes > self.MAX_TOOL_BYTES):
            self._reject(delta, 'safety budget exceeded')

        progress = self.calls.setdefault(delta.index, _ArgumentProgress())
        progress.empty_deltas = 0 if delta.arguments else progress.empty_deltas + 1
        if progress.empty_deltas > self.MAX_EMPTY_DELTAS:
            self._reject(delta, 'consecutive empty argument deltas exceeded limit')

        # Track string/escape boundaries only; the assembler validates complete JSON.
        for char in delta.arguments:
            if progress.in_string:
                if progress.escaped:
                    progress.escaped = False
                elif char == "\\":
                    progress.escaped = True
                elif char == '"':
                    progress.in_string = False
            elif char == '"':
                progress.in_string = True
            progress.whitespace = (progress.whitespace + 1
                                   if not progress.in_string and char in ' \t\r\n' else 0)
            if progress.whitespace > self.MAX_JSON_WHITESPACE:
                self._reject(delta, 'consecutive whitespace outside JSON strings exceeded limit')

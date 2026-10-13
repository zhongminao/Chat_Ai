class TextBuffer:
    def __init__(self, flush_chars: int = 1):
        self.flush_chars = flush_chars
        self.parts: list[str] = []

    def add(self, text: str) -> str | None:
        self.parts.append(text)
        if sum(map(len, self.parts)) >= self.flush_chars:
            return self.flush()
        return None

    def flush(self) -> str:
        text = "".join(self.parts)
        self.parts.clear()
        return text

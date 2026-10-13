from html.parser import HTMLParser
from os import getenv
from typing import Annotated
from urllib.parse import urlparse

import httpx
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

server = MCPServer("search")
SEARCH_URL = getenv("SEARXNG_URL", "http://127.0.0.1:8888")


class SearchItem(BaseModel):
    title: str
    url: str
    content: str


class SearchResult(BaseModel):
    query: str
    results: list[SearchItem]
    unresponsive_engines: list[str]


class FetchResult(BaseModel):
    url: str
    title: str
    text: str


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        value = " ".join(data.split())
        if not value:
            return
        if self.in_title:
            self.title += value + " "
        elif not self.skip:
            self.parts.append(value)


@server.tool(description="搜索网页，返回标题、链接和摘要。", structured_output=True)
def search(query: Annotated[str, Field(min_length=1)],
           limit: Annotated[int, Field(ge=1, le=20)] = 5) -> SearchResult:
    response = httpx.get(
        f"{SEARCH_URL}/search",
        params={"q": query, "format": "json"},
        timeout=30,
        trust_env=False,
    )
    response.raise_for_status()
    data = response.json()
    items = [
        SearchItem(
            title=item.get("title", ""),
            url=item.get("url", ""),
            content=item.get("content", ""),
        )
        for item in data.get("results", [])[:limit]
    ]
    failed = [
        " / ".join(map(str, item)) if isinstance(item, list) else str(item)
        for item in data.get("unresponsive_engines", [])
    ]
    return SearchResult(query=query, results=items, unresponsive_engines=failed)


@server.tool(description="读取公开网页正文。", structured_output=True)
def fetch_url(url: Annotated[str, Field(min_length=1)]) -> FetchResult:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("只支持 http 或 https URL")
    response = httpx.get(
        url,
        headers={"User-Agent": "chat-ai-fetch/1.0"},
        follow_redirects=True,
        timeout=20,
        trust_env=False,
    )
    response.raise_for_status()
    parser = TextParser()
    parser.feed(response.text)
    text = " ".join(parser.parts)
    return FetchResult(
        url=str(response.url),
        title=parser.title.strip(),
        text=text[:20000],
    )


if __name__ == "__main__":
    server.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8766,
        stateless_http=True,
        json_response=True,
    )

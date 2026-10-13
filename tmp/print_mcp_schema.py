import argparse
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main(url: str):
    async with streamable_http_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            for tool in result.tools:
                print(tool.model_dump_json(by_alias=True, exclude_none=True, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="获取并打印 MCP 工具 schema")
    parser.add_argument("url", nargs="?", default="http://127.0.0.1:8766/mcp")
    asyncio.run(main(parser.parse_args().url))

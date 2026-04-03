from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession
import asyncio

async def main():
    app_url = "http://localhost:8000/mcp/"
    async with streamable_http_client(app_url) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            await session.initialize()
            tools = await session.list_tools()
            print("Tools available:", tools)

if __name__ == "__main__":
    asyncio.run(main())

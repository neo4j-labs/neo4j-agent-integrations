from databricks.sdk import WorkspaceClient
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession
import asyncio

client = WorkspaceClient()

async def main():
    headers = client.config.authenticate()
    app_url = "https://your.app.url.databricksapps.com/mcp/"
    async with streamable_http_client(app_url,  headers=headers) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Tools available:", tools)

if __name__ == "__main__":
    asyncio.run(main())

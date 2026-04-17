"""Test the Devpost MCP server."""

import asyncio
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters


async def test():
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "devpost_mcp.server"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List tools
            tools = await session.list_tools()
            print(f"Available tools: {[t.name for t in tools.tools]}")
            
            # Test list_hackathons
            print("\n--- Testing list_hackathons ---")
            result = await session.call_tool("list_hackathons", {"limit": 3, "open_state": "open"})
            print(result.content[0].text[:500])
            
            # Test search
            print("\n--- Testing search_hackathons ---")
            result = await session.call_tool("search_hackathons", {"query": "AI", "limit": 2})
            print(result.content[0].text[:500])


if __name__ == "__main__":
    asyncio.run(test())

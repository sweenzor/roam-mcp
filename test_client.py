#!/usr/bin/env python3
import asyncio
from mcp.client import MCP

async def main():
    # Connect to the local MCP server
    mcp = MCP(base_url="http://localhost:8000")
    
    # Call the hello_world tool
    result = await mcp.hello_world(name="MCP Tester")
    print(f"Tool response: {result}")
    
    # You can also list available tools
    tools = await mcp.list_tools()
    print("\nAvailable tools:")
    for tool in tools:
        print(f"- {tool['name']}: {tool['description']}")

if __name__ == "__main__":
    asyncio.run(main())
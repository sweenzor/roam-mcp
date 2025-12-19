#!/usr/bin/env python3
"""Simple test client for the Roam MCP server.

This script demonstrates connecting to the server and calling tools.
"""
import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


async def run_client_demo() -> None:
    """Demo the server by calling various tools."""
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "mcp_server_roam"],
    )

    try:
        # Connect to the server
        print("Connecting to the server...")
        async with (
            stdio_client(server_params) as (read, write),
            ClientSession(read, write) as session,
        ):
            # Initialize the connection
            print("Initializing connection...")
            await session.initialize()

            # List available tools
            print("\nListing available tools...")
            tools_result = await session.list_tools()
            print(f"Tools result: {tools_result}")

            # Call the get_page tool
            print("\nTesting get_page tool:")
            try:
                result = await session.call_tool("get_page", {"title": "Test Page"})
                print(f"Response: {result}")
            except Exception as e:
                print(f"Error calling get_page: {e}")

            # Call the create_block tool
            print("\nTesting create_block tool:")
            try:
                result = await session.call_tool(
                    "create_block",
                    {"content": "This is a test block", "title": "Test Page"},
                )
                print(f"Response: {result}")
            except Exception as e:
                print(f"Error calling create_block: {e}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(run_client_demo())

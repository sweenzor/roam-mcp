#!/usr/bin/env python3
"""Simple test client for the Roam MCP server.

This script sends a request to test the roam_hello_world tool.
"""
import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


async def test_server() -> None:
    """Test the server by calling various tools."""
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

            # Call the hello_world tool
            print("\nTesting roam_hello_world tool:")
            try:
                result = await session.call_tool(
                    "roam_hello_world", {"name": "Tester"}
                )
                print(f"Response: {result}")
            except Exception as e:
                print(f"Error calling roam_hello_world: {e}")

            # Call the fetch_page_by_title tool
            print("\nTesting roam_fetch_page_by_title tool:")
            try:
                result = await session.call_tool(
                    "roam_fetch_page_by_title", {"title": "Test Page"}
                )
                print(f"Response: {result}")
            except Exception as e:
                print(f"Error calling roam_fetch_page_by_title: {e}")

            # Call the create_block tool
            print("\nTesting roam_create_block tool:")
            try:
                result = await session.call_tool("roam_create_block", {
                    "content": "This is a test block",
                    "title": "Test Page"
                })
                print(f"Response: {result}")
            except Exception as e:
                print(f"Error calling roam_create_block: {e}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_server())

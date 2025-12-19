#!/usr/bin/env python3
"""Test script for the Roam MCP tools.

This script programmatically tests the MCP server tools by connecting to the
server and calling each tool.
"""
import asyncio
import logging
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_server() -> None:
    """Test the MCP server tools by connecting to it and calling each tool."""
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "mcp_server_roam"],
    )

    try:
        print("Connecting to the server...")
        async with (
            stdio_client(server_params) as (read, write),
            ClientSession(read, write) as session,
        ):
            print("Initializing connection...")
            await session.initialize()

            # List available tools
            print("\nListing available tools...")
            tools_result = await session.list_tools()
            print(f"Found {len(tools_result.tools)} tools:")
            for tool in tools_result.tools:
                print(f"- {tool.name}: {tool.description}")

            # Test get_page tool
            print("\nTesting get_page tool...")
            page_title = "April 6th, 2025"
            try:
                page_result = await session.call_tool("get_page", {"title": page_title})
                print(f"Result for '{page_title}':")
                print(page_result)
            except Exception as e:
                print(f"Error calling get_page: {e}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_server())

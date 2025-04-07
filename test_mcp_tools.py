#!/usr/bin/env python3
"""
Test script for the Roam MCP tools.
This script programmatically tests the MCP server tools by connecting to the server
and calling each tool.
"""

import asyncio
import json
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_server():
    """Test the MCP server tools by connecting to it and calling each tool."""
    # Configure the client
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "mcp_server_roam"],
    )
    
    try:
        # Connect to the server
        print("Connecting to the server...")
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize the connection
                print("Initializing connection...")
                await session.initialize()
                
                # List available tools
                print("\nListing available tools...")
                tools_result = await session.list_tools()
                print(f"Found {len(tools_result.tools)} tools:")
                for tool in tools_result.tools:
                    print(f"- {tool.name}: {tool.description}")
                
                # Test hello world tool
                print("\nTesting roam_hello_world tool...")
                try:
                    hello_result = await session.call_tool("roam_hello_world", {"name": "MCP Tester"})
                    print(f"Result: {hello_result}")
                except Exception as e:
                    print(f"Error calling roam_hello_world: {e}")
                
                # Test get_page_markdown tool
                print("\nTesting roam_get_page_markdown tool...")
                page_title = "April 6th, 2025"
                try:
                    page_result = await session.call_tool("roam_get_page_markdown", {"title": page_title})
                    print(f"Result for '{page_title}':")
                    print(page_result)
                except Exception as e:
                    print(f"Error calling roam_get_page_markdown: {e}")
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_server())
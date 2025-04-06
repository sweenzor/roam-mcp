#!/usr/bin/env python3
from mcp.server.fastmcp import FastMCP

# Create MCP server
mcp = FastMCP("simple-mcp")

# Define a simple tool
@mcp.tool()
async def hello_world(name: str = "world") -> str:
    """A simple greeting tool.
    
    Args:
        name: Name to greet
    """
    return f"Hello, {name}!"

if __name__ == "__main__":
    print("Starting simple MCP server...")
    mcp.run()
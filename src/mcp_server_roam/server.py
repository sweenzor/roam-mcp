"""
Roam Research MCP Server - Simple Hello World Example
"""
from mcp.server.fastmcp import FastMCP

# Create an MCP server
mcp = FastMCP("Roam Research MCP")


# Add a simple greeting tool
@mcp.tool()
def roam_hello_world(name: str = "World") -> str:
    """
    A simple hello world tool for Roam Research MCP.
    
    Args:
        name: The name to greet. Defaults to "World".
        
    Returns:
        A greeting message.
    """
    return f"Hello, {name}! This is the Roam Research MCP server."


# Add a simple resource that returns information about Roam Research
@mcp.resource("roam://info")
def get_roam_info() -> str:
    """
    Get basic information about Roam Research.
    
    Returns:
        Basic information about Roam Research as markdown text.
    """
    return """
# Roam Research

Roam Research is a note-taking and knowledge management application that focuses on networked thought.

Key features:
- **Bi-directional linking**: Connect notes and concepts effortlessly
- **Block-based structure**: Each bullet point is a block with a unique ID
- **Daily notes**: Automatically creates a new page for each day
- **Graph view**: Visualize connections between your notes
- **Queries**: Find and display information across your knowledge graph
    """


if __name__ == "__main__":
    # Run the MCP server
    mcp.run()
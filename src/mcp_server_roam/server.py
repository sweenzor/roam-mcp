import logging
import os
from typing import Any, Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from pydantic import BaseModel
from enum import Enum
from dotenv import load_dotenv

# Import our Roam API client
# from src.mcp_server_roam.roam_api import RoamAPI

# Load environment variables from .env file
load_dotenv()

# Pydantic models for tool inputs
class RoamHelloWorld(BaseModel):
    name: str = "World"

class RoamFetchPageByTitle(BaseModel):
    title: str

class RoamCreateBlock(BaseModel):
    content: str
    page_uid: Optional[str] = None
    title: Optional[str] = None

# Enum for tool names
class RoamTools(str, Enum):
    HELLO_WORLD = "roam_hello_world"
    FETCH_PAGE_BY_TITLE = "roam_fetch_page_by_title"
    CREATE_BLOCK = "roam_create_block"

# Tool implementation functions
def roam_hello_world(name: str = "World") -> str:
    """Simple hello world tool for Roam Research MCP."""
    return f"Hello, {name}! This is the Roam Research MCP server."

def roam_fetch_page_by_title(title: str) -> str:
    """
    Fetch a page's content by title.
    
    This uses the Roam API to fetch the page content and converts it to a nested markdown format.
    """
    # Mock implementation for now
    return f"Contents of page '{title}':\n\n- This is a mock implementation\n  - We would fetch the actual page content from Roam\n  - And convert it to markdown format\n- With proper formatting"
    
    # Actual implementation (commented out until we have a working API token)
    """
    try:
        # Initialize Roam API client
        roam = RoamAPI()
        
        # Get the page by title
        page_data = roam.get_page(title)
        
        # Convert page data to markdown (simplified for now)
        markdown = f"# {title}\n\n"
        
        # Process children blocks
        if "children" in page_data and page_data["children"]:
            for child in page_data["children"]:
                markdown += f"- {child.get('string', '')}\n"
                # Process nested children (simplistic implementation)
                if "children" in child and child["children"]:
                    for grandchild in child["children"]:
                        markdown += f"  - {grandchild.get('string', '')}\n"
        
        return markdown
    except Exception as e:
        return f"Error fetching page: {str(e)}"
    """

def roam_create_block(content: str, page_uid: Optional[str] = None, title: Optional[str] = None) -> dict[str, Any]:
    """
    Create a new block in a Roam page.
    
    This uses the Roam API to create a new block in the specified page,
    or in today's Daily Note if no page is specified.
    """
    # Mock implementation for now
    target = title if title else page_uid if page_uid else "Today's Daily Note"
    return {
        "success": True,
        "block_uid": "mock-block-uid",
        "parent_uid": "mock-parent-uid",
        "message": f"Created block in '{target}' with content: {content}"
    }
    
    # Actual implementation (commented out until we have a working API token)
    """
    try:
        # Initialize Roam API client
        roam = RoamAPI()
        
        # Create the block
        result = roam.create_block(content, page_uid, title)
        
        return {
            "success": True,
            "block_uid": result.get("uid", "unknown"),
            "parent_uid": result.get("parent-uid", "unknown"),
            "message": f"Created block successfully with content: {content}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to create block: {str(e)}"
        }
    """

# Create the server instance - this is what mcp dev looks for
server = Server("mcp-roam")

# Set up the tools
@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name=RoamTools.HELLO_WORLD,
            description="Simple hello world greeting from Roam MCP server",
            inputSchema=RoamHelloWorld.schema(),
        ),
        Tool(
            name=RoamTools.FETCH_PAGE_BY_TITLE,
            description="Fetch and read a page's content by title",
            inputSchema=RoamFetchPageByTitle.schema(),
        ),
        Tool(
            name=RoamTools.CREATE_BLOCK,
            description="Add a new block to a Roam page",
            inputSchema=RoamCreateBlock.schema(),
        ),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    match name:
        case RoamTools.HELLO_WORLD:
            result = roam_hello_world(arguments.get("name", "World"))
            return [TextContent(
                type="text",
                text=result
            )]
            
        case RoamTools.FETCH_PAGE_BY_TITLE:
            page_content = roam_fetch_page_by_title(arguments["title"])
            return [TextContent(
                type="text",
                text=page_content
            )]
            
        case RoamTools.CREATE_BLOCK:
            result = roam_create_block(
                arguments["content"],
                arguments.get("page_uid"),
                arguments.get("title")
            )
            return [TextContent(
                type="text",
                text=str(result)
            )]
            
        case _:
            raise ValueError(f"Unknown tool: {name}")

async def serve() -> None:
    """Main server function that initializes and runs the MCP server."""
    logger = logging.getLogger(__name__)
    
    # Initialize and run the server
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)
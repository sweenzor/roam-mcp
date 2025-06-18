from typing import Any, Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from pydantic import BaseModel
from enum import Enum
from dotenv import load_dotenv

# Import our Roam API client
from mcp_server_roam.roam_api import RoamAPI

# Load environment variables from .env file
load_dotenv()

def process_blocks(blocks, depth: int) -> str:
    """
    Recursively process blocks and convert them to markdown.
    
    Args:
        blocks: List of blocks to process
        depth: Current nesting level (0 = top level)
        
    Returns:
        Markdown-formatted blocks with proper indentation
    """
    result = ""
    indent = "  " * depth
    
    for block in blocks:
        # Get the block string content
        block_string = block.get(":block/string", "")
        if not block_string:  # Skip empty blocks
            continue
            
        # Add this block with proper indentation
        result += f"{indent}- {block_string}\n"
        
        # Process children recursively if they exist
        if ":block/children" in block and block[":block/children"]:
            result += process_blocks(block[":block/children"], depth + 1)
    
    return result

# Pydantic models for tool inputs
class RoamHelloWorld(BaseModel):
    name: str = "World"

class RoamFetchPageByTitle(BaseModel):
    title: str

class RoamGetPageMarkdown(BaseModel):
    title: str

class RoamCreateBlock(BaseModel):
    content: str
    page_uid: Optional[str] = None
    title: Optional[str] = None

class RoamContext(BaseModel):
    days: int = 10
    max_references: int = 10

class RoamDebugDailyNotes(BaseModel):
    pass

# Enum for tool names
class RoamTools(str, Enum):
    HELLO_WORLD = "roam_hello_world"
    FETCH_PAGE_BY_TITLE = "roam_fetch_page_by_title"
    GET_PAGE_MARKDOWN = "roam_get_page_markdown"
    CREATE_BLOCK = "roam_create_block"
    CONTEXT = "roam_context"
    DEBUG_DAILY_NOTES = "roam_debug_daily_notes"

# Tool implementation functions
def roam_hello_world(name: str = "World") -> str:
    """Simple hello world tool for Roam Research MCP."""
    return f"Hello, {name}! This is the Roam Research MCP server."

def roam_get_page_markdown(title: str) -> str:
    """
    Retrieve a page's content in clean markdown format.
    
    This uses the Roam API to fetch the page content and converts it to a well-formatted
    markdown representation, suitable for display or further processing.
    
    Args:
        title: Title of the page to fetch
        
    Returns:
        Markdown-formatted page content with proper nesting and references
    """
    try:
        # Initialize Roam API client
        roam = RoamAPI()
        
        # Get the page by title
        page_data = roam.get_page(title)
        
        # Create markdown output
        markdown = f"# {title}\n\n"
        
        # Process children blocks recursively
        if ":block/children" in page_data and page_data[":block/children"]:
            markdown += process_blocks(page_data[":block/children"], 0)
        
        return markdown
    except Exception as e:
        return f"Error fetching page: {str(e)}"

def roam_fetch_page_by_title(title: str) -> str:
    """
    Fetch a page's content by title.
    
    This uses the Roam API to fetch the page content and converts it to a nested markdown format.
    """
    try:
        # Initialize Roam API client
        roam = RoamAPI()
        
        # Get the page by title
        page_data = roam.get_page(title)
        
        # Convert page data to markdown (simplified for now)
        markdown = f"# {title}\n\n"
        
        # Process children blocks
        if ":block/children" in page_data and page_data[":block/children"]:
            for child in page_data[":block/children"]:
                # Get the block string content, default to empty string if not found
                block_string = child.get(":block/string", "")
                markdown += f"- {block_string}\n"
                
                # Process nested children (simplistic implementation)
                if ":block/children" in child and child[":block/children"]:
                    for grandchild in child[":block/children"]:
                        grandchild_string = grandchild.get(":block/string", "")
                        markdown += f"  - {grandchild_string}\n"
                        
                        # Process one more level of nesting
                        if ":block/children" in grandchild and grandchild[":block/children"]:
                            for great_grandchild in grandchild[":block/children"]:
                                great_grandchild_string = great_grandchild.get(":block/string", "")
                                markdown += f"    - {great_grandchild_string}\n"
        
        return markdown
    except Exception as e:
        return f"Error fetching page: {str(e)}"

def roam_create_block(content: str, page_uid: Optional[str] = None, title: Optional[str] = None) -> dict[str, Any]:
    """
    Create a new block in a Roam page.
    
    This uses the Roam API to create a new block in the specified page,
    or in today's Daily Note if no page is specified.
    """
    try:
        # Initialize Roam API client
        roam = RoamAPI()
        
        # If title is provided and page_uid is not, first get the page UID
        if title and not page_uid:
            try:
                # Find the page by title
                query = f'[:find ?uid :where [?e :node/title "{title}"] [?e :block/uid ?uid]]'
                results = roam.run_query(query)
                
                if results and len(results) > 0:
                    page_uid = results[0][0]
                else:
                    # If page doesn't exist, we might want to create it first
                    return {
                        "success": False,
                        "error": f"Page with title '{title}' not found",
                        "message": f"Failed to create block: Page with title '{title}' not found"
                    }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"Failed to find page by title: {str(e)}"
                }
                
        # Create the block
        result = roam.create_block(content, page_uid)
        
        return {
            "success": True,
            "block_uid": result.get("uid", "unknown"),
            "parent_uid": page_uid or "daily-note",
            "message": f"Created block successfully with content: {content}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to create block: {str(e)}"
        }

def roam_context(days: int = 10, max_references: int = 10) -> str:
    """
    Get the last N days of daily notes with their linked references for context.
    
    Args:
        days: Number of days to fetch (default: 10)
        
    Returns:
        Markdown formatted context with daily notes and linked references
    """
    try:
        # Initialize Roam API client
        roam = RoamAPI()
        
        # Get the context
        return roam.get_daily_notes_context(days)
    except Exception as e:
        return f"Error fetching context: {str(e)}"

def roam_debug_daily_notes() -> str:
    """
    Debug function to test different daily note formats and show what exists.
    
    Returns:
        Debug information about daily note formats and existing pages
    """
    try:
        # Initialize Roam API client
        roam = RoamAPI()
        
        # Get the detected format
        detected_format = roam.find_daily_note_format()
        
        from datetime import datetime, timedelta
        debug_info = ["# Daily Notes Debug\n"]
        debug_info.append(f"**Detected format**: `{detected_format}`\n")
        
        # Test the last 3 days with the detected format
        for i in range(3):
            date = datetime.now() - timedelta(days=i)
            
            # Handle ordinal suffixes for formats that need them
            if detected_format in ["%B %dth, %Y", "%B %dst, %Y", "%B %dnd, %Y", "%B %drd, %Y"]:
                day = date.day
                if day in [1, 21, 31]:
                    suffix = "st"
                elif day in [2, 22]:
                    suffix = "nd" 
                elif day in [3, 23]:
                    suffix = "rd"
                else:
                    suffix = "th"
                
                date_str = date.strftime(f"%B %d{suffix}, %Y")
            else:
                date_str = date.strftime(detected_format)
            
            try:
                # Try to get the page
                page_data = roam.get_page(date_str)
                debug_info.append(f"✅ **{date_str}**: Found (has {len(page_data.get(':block/children', []))} children)")
            except ValueError:
                debug_info.append(f"❌ **{date_str}**: Not found")
        
        return "\n".join(debug_info)
    except Exception as e:
        return f"Error in debug: {str(e)}"

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
            name=RoamTools.GET_PAGE_MARKDOWN,
            description="Retrieve a page's content in clean markdown format",
            inputSchema=RoamGetPageMarkdown.schema(),
        ),
        Tool(
            name=RoamTools.CREATE_BLOCK,
            description="Add a new block to a Roam page",
            inputSchema=RoamCreateBlock.schema(),
        ),
        Tool(
            name=RoamTools.CONTEXT,
            description="Get the last N days of daily notes with their linked references for context",
            inputSchema=RoamContext.schema(),
        ),
        Tool(
            name=RoamTools.DEBUG_DAILY_NOTES,
            description="Debug daily note formats and show what daily notes exist",
            inputSchema=RoamDebugDailyNotes.schema(),
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
            
        case RoamTools.GET_PAGE_MARKDOWN:
            markdown_content = roam_get_page_markdown(arguments["title"])
            return [TextContent(
                type="text",
                text=markdown_content
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
            
        case RoamTools.CONTEXT:
            context_content = roam_context(
                arguments.get("days", 10),
                arguments.get("max_references", 10)
            )
            return [TextContent(
                type="text",
                text=context_content
            )]
            
        case RoamTools.DEBUG_DAILY_NOTES:
            debug_content = roam_debug_daily_notes()
            return [TextContent(
                type="text",
                text=debug_content
            )]
            
        case _:
            raise ValueError(f"Unknown tool: {name}")

async def serve() -> None:
    """Main server function that initializes and runs the MCP server."""
    # Initialize and run the server
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)
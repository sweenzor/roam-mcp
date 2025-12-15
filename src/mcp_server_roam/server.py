"""MCP server implementation for Roam Research API."""
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel

# Import our Roam API client and custom exceptions
from mcp_server_roam.roam_api import (
    PageNotFoundError,
    RoamAPI,
    RoamAPIError,
    ordinal_suffix,
)

# Load environment variables from .env file
load_dotenv()

# Singleton instance for RoamAPI client
_roam_client: RoamAPI | None = None


def get_roam_client() -> RoamAPI:
    """Get or create the singleton RoamAPI client instance."""
    global _roam_client
    if _roam_client is None:
        _roam_client = RoamAPI()
    return _roam_client


# Pydantic models for tool inputs
class RoamHelloWorld(BaseModel):
    """Input schema for hello_world tool."""

    name: str = "World"


class RoamGetPageMarkdown(BaseModel):
    """Input schema for get_page_markdown tool."""

    title: str


class RoamCreateBlock(BaseModel):
    """Input schema for create_block tool."""

    content: str
    page_uid: str | None = None
    title: str | None = None


class RoamContext(BaseModel):
    """Input schema for context tool."""

    days: int = 10
    max_references: int = 10


class RoamDebugDailyNotes(BaseModel):
    """Input schema for debug_daily_notes tool."""

    pass


# Tool implementation functions
def roam_hello_world(name: str = "World") -> str:
    """Simple hello world tool for Roam Research MCP."""
    return f"Hello, {name}! This is the Roam Research MCP server."


def roam_get_page_markdown(title: str) -> str:
    """Retrieve a page's content in clean markdown format.

    This uses the Roam API to fetch the page content and converts it to a well-formatted
    markdown representation, suitable for display or further processing.

    Args:
        title: Title of the page to fetch

    Returns:
        Markdown-formatted page content with proper nesting and references
    """
    try:
        # Get singleton Roam API client
        roam = get_roam_client()

        # Get the page by title
        page_data = roam.get_page(title)

        # Create markdown output
        markdown = f"# {title}\n\n"

        # Process children blocks recursively using unified function from roam_api
        if ":block/children" in page_data and page_data[":block/children"]:
            markdown += roam.process_blocks(page_data[":block/children"], 0)

        return markdown
    except PageNotFoundError as e:
        # Page not found error
        return f"Error: {str(e)}"
    except RoamAPIError as e:
        return f"Error fetching page: {str(e)}"


def roam_create_block(
    content: str, page_uid: str | None = None, title: str | None = None
) -> str:
    """Create a new block in a Roam page."""
    try:
        roam = get_roam_client()

        # If title is provided, look up the page UID
        if title and not page_uid:
            query = (
                f'[:find ?uid :where [?e :node/title "{title}"] '
                '[?e :block/uid ?uid]]'
            )
            results = roam.run_query(query)
            if not results:
                return f"Error: Page '{title}' not found"
            page_uid = results[0][0]

        result = roam.create_block(content, page_uid)
        block_uid = result.get("uid", "unknown")
        return f"Created block {block_uid} with content: {content}"

    except RoamAPIError as e:
        return f"Error creating block: {e}"


def roam_context(days: int = 10, max_references: int = 10) -> str:
    """Get the last N days of daily notes with their linked references for context.

    Args:
        days: Number of days to fetch (default: 10, range: 1-30).
        max_references: Max references per daily note (default: 10, range: 1-100).

    Returns:
        Markdown formatted context with daily notes and linked references.
    """
    try:
        # Validate input parameters
        if not isinstance(days, int) or days < 1 or days > 30:
            return "Error: 'days' parameter must be an integer between 1 and 30"
        max_ref_invalid = (
            not isinstance(max_references, int)
            or max_references < 1
            or max_references > 100
        )
        if max_ref_invalid:
            return "Error: 'max_references' must be an integer between 1 and 100"

        # Get singleton Roam API client
        roam = get_roam_client()

        # Get the context
        return roam.get_daily_notes_context(days, max_references)
    except RoamAPIError as e:
        return f"Error fetching context: {str(e)}"


def roam_debug_daily_notes() -> str:
    """Debug function to test different daily note formats and show what exists.

    Returns:
        Debug information about daily note formats and existing pages
    """
    try:
        # Get singleton Roam API client
        roam = get_roam_client()

        # Get the detected format
        detected_format = roam.find_daily_note_format()

        from datetime import datetime, timedelta
        debug_info = ["# Daily Notes Debug\n"]
        debug_info.append(f"**Detected format**: `{detected_format}`\n")

        # Test the last 3 days with the detected format
        ordinal_formats = [
            "%B %dth, %Y", "%B %dst, %Y", "%B %dnd, %Y", "%B %drd, %Y"
        ]
        for i in range(3):
            date = datetime.now() - timedelta(days=i)

            if detected_format in ordinal_formats:
                date_str = date.strftime(f"%B %d{ordinal_suffix(date.day)}, %Y")
            else:
                date_str = date.strftime(detected_format)

            try:
                # Try to get the page
                page_data = roam.get_page(date_str)
                children_count = len(page_data.get(':block/children', []))
                debug_info.append(f"✅ **{date_str}**: Found ({children_count})")
            except PageNotFoundError:
                debug_info.append(f"❌ **{date_str}**: Not found")
            except RoamAPIError as e:
                debug_info.append(f"❌ **{date_str}**: Error - {str(e)}")

        return "\n".join(debug_info)
    except RoamAPIError as e:
        return f"Error: {str(e)}"


# Create the server instance - this is what mcp dev looks for
server = Server("mcp-roam")


# Set up the tools
@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return list of available tools."""
    return [
        Tool(
            name="roam_hello_world",
            description="Simple hello world greeting from Roam MCP server",
            inputSchema=RoamHelloWorld.schema(),
        ),
        Tool(
            name="roam_get_page_markdown",
            description="Retrieve a page's content in clean markdown format",
            inputSchema=RoamGetPageMarkdown.schema(),
        ),
        Tool(
            name="roam_create_block",
            description="Add a new block to a Roam page",
            inputSchema=RoamCreateBlock.schema(),
        ),
        Tool(
            name="roam_context",
            description="Get daily notes with their linked references for context",
            inputSchema=RoamContext.schema(),
        ),
        Tool(
            name="roam_debug_daily_notes",
            description="Debug daily note formats and show what daily notes exist",
            inputSchema=RoamDebugDailyNotes.schema(),
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    match name:
        case "roam_hello_world":
            result = roam_hello_world(arguments.get("name", "World"))
        case "roam_get_page_markdown":
            result = roam_get_page_markdown(arguments["title"])
        case "roam_create_block":
            result = roam_create_block(
                arguments["content"],
                arguments.get("page_uid"),
                arguments.get("title")
            )
        case "roam_context":
            result = roam_context(
                arguments.get("days", 10),
                arguments.get("max_references", 10)
            )
        case "roam_debug_daily_notes":
            result = roam_debug_daily_notes()
        case _:
            raise ValueError(f"Unknown tool: {name}")

    return [TextContent(type="text", text=str(result))]


async def serve() -> None:
    """Main server function that initializes and runs the MCP server."""
    # Initialize and run the server
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)

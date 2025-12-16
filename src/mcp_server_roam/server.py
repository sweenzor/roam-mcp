"""MCP server implementation for Roam Research API."""
import json
import logging
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel

from mcp_server_roam.embedding import get_embedding_service
from mcp_server_roam.roam_api import (
    ORDINAL_DATE_FORMATS,
    BlockNotFoundError,
    InvalidQueryError,
    PageNotFoundError,
    RoamAPI,
    RoamAPIError,
    ordinal_suffix,
)
from mcp_server_roam.vector_store import SyncStatus, get_vector_store

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Singleton instance for RoamAPI client
_roam_client: RoamAPI | None = None


def get_roam_client() -> RoamAPI:
    """Get or create the singleton RoamAPI client instance.

    Returns:
        The singleton RoamAPI client instance.
    """
    global _roam_client
    if _roam_client is None:
        _roam_client = RoamAPI()
    return _roam_client


# Pydantic models for tool inputs
class HelloWorld(BaseModel):
    """Input schema for hello_world tool."""

    name: str = "World"


class GetPage(BaseModel):
    """Input schema for get_page_markdown tool."""

    title: str


class CreateBlock(BaseModel):
    """Input schema for create_block tool."""

    content: str
    page_uid: str | None = None
    title: str | None = None


class DailyContext(BaseModel):
    """Input schema for context tool."""

    days: int = 10
    max_references: int = 10


class DebugDailyNotes(BaseModel):
    """Input schema for debug_daily_notes tool."""

    pass


class SyncIndex(BaseModel):
    """Input schema for sync_index tool."""

    full: bool = False


class SemanticSearch(BaseModel):
    """Input schema for semantic_search tool."""

    query: str
    limit: int = 10
    include_context: bool = True


class GetBlockContext(BaseModel):
    """Input schema for get_block_context tool."""

    uid: str


class SearchByText(BaseModel):
    """Input schema for search_by_text tool."""

    text: str
    page_title: str | None = None
    limit: int = 20


class RawQuery(BaseModel):
    """Input schema for raw_query tool."""

    query: str
    args: list | None = None


class GetBacklinks(BaseModel):
    """Input schema for get_backlinks tool."""

    page_title: str
    limit: int = 20


# Tool implementation functions
def hello_world(name: str = "World") -> str:
    """Simple hello world tool for Roam Research MCP.

    Args:
        name: The name to greet.

    Returns:
        A greeting message.
    """
    return f"Hello, {name}! This is the Roam Research MCP server."


def get_page(title: str) -> str:
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


def create_block(
    content: str, page_uid: str | None = None, title: str | None = None
) -> str:
    """Create a new block in a Roam page.

    Args:
        content: The content text for the new block.
        page_uid: Optional UID of the page to add the block to.
        title: Optional title of the page to add the block to.

    Returns:
        A confirmation message with the created block UID.
    """
    try:
        roam = get_roam_client()

        # If title is provided, look up the page UID
        if title and not page_uid:
            # Sanitize title to prevent query injection
            sanitized_title = RoamAPI._sanitize_query_input(title)
            query = (
                f'[:find ?uid :where [?e :node/title "{sanitized_title}"] '
                "[?e :block/uid ?uid]]"
            )
            results = roam.run_query(query)
            if not results:
                return f"Error: Page '{title}' not found"
            page_uid = results[0][0]

        result = roam.create_block(content, page_uid)
        block_uid = result.get("uid", "unknown")
        return f"Created block {block_uid} with content: {content}"

    except InvalidQueryError as e:
        return f"Error: Invalid input - {e}"
    except RoamAPIError as e:
        return f"Error creating block: {e}"


def daily_context(days: int = 10, max_references: int = 10) -> str:
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


def debug_daily_notes() -> str:
    """Debug function to test different daily note formats and show what exists.

    Returns:
        Debug information about daily note formats and existing pages.
    """
    try:
        # Get singleton Roam API client
        roam = get_roam_client()

        # Get the detected format
        detected_format = roam.find_daily_note_format()

        debug_info = ["# Daily Notes Debug\n"]
        debug_info.append(f"**Detected format**: `{detected_format}`\n")

        # Test the last 3 days with the detected format
        for i in range(3):
            date = datetime.now() - timedelta(days=i)

            if detected_format in ORDINAL_DATE_FORMATS:
                date_str = date.strftime(f"%B %d{ordinal_suffix(date.day)}, %Y")
            else:
                date_str = date.strftime(detected_format)

            try:
                # Try to get the page
                page_data = roam.get_page(date_str)
                children_count = len(page_data.get(":block/children", []))
                debug_info.append(f"✅ **{date_str}**: Found ({children_count})")
            except PageNotFoundError:
                debug_info.append(f"❌ **{date_str}**: Not found")
            except RoamAPIError as e:
                debug_info.append(f"❌ **{date_str}**: Error - {str(e)}")

        return "\n".join(debug_info)
    except RoamAPIError as e:
        return f"Error: {str(e)}"


# Constants for sync_index
SYNC_BATCH_SIZE = 64
SYNC_COMMIT_INTERVAL = 500


def sync_index(full: bool = False) -> str:
    """Build or update the vector index for semantic search.

    Args:
        full: If True, perform a full resync (drops existing data).

    Returns:
        Status message with sync statistics.
    """
    start_time = time.time()

    try:
        roam = get_roam_client()
        store = get_vector_store(roam.graph_name)
        embedding_service = get_embedding_service()

        # Check current sync status
        current_status = store.get_sync_status()

        # Determine if we need a full sync
        do_full_sync = full or current_status == SyncStatus.NOT_INITIALIZED

        if do_full_sync:
            logger.info("Starting full sync - dropping existing data")
            store.drop_all_data()
            store.set_sync_status(SyncStatus.IN_PROGRESS)
            fetch_start = time.time()
            blocks = roam.get_all_blocks_for_sync()
            logger.info(
                "Fetched %d blocks from Roam API in %.1fs",
                len(blocks), time.time() - fetch_start
            )
        else:
            # Incremental sync - get blocks modified since last sync
            last_timestamp = store.get_last_sync_timestamp()
            if last_timestamp is None:
                # No previous sync, do full
                logger.info("No previous sync found - performing full sync")
                store.set_sync_status(SyncStatus.IN_PROGRESS)
                fetch_start = time.time()
                blocks = roam.get_all_blocks_for_sync()
                logger.info(
                    "Fetched %d blocks from Roam API in %.1fs",
                    len(blocks), time.time() - fetch_start
                )
            else:
                store.set_sync_status(SyncStatus.IN_PROGRESS)
                logger.debug("Incremental sync from timestamp %d", last_timestamp)
                blocks = roam.get_blocks_modified_since(last_timestamp)
                logger.info(
                    "Found %d modified blocks for incremental sync", len(blocks)
                )

        if not blocks:
            store.set_sync_status(SyncStatus.COMPLETED)
            elapsed = time.time() - start_time
            return f"No blocks to sync. Completed in {elapsed:.1f}s."

        # Store block metadata
        store.upsert_blocks(blocks)
        logger.debug("Stored metadata for %d blocks", len(blocks))

        # Generate and store embeddings in batches
        embed_start = time.time()
        total_embedded = 0
        num_batches = (len(blocks) + SYNC_BATCH_SIZE - 1) // SYNC_BATCH_SIZE
        for batch_num, i in enumerate(range(0, len(blocks), SYNC_BATCH_SIZE), 1):
            batch = blocks[i:i + SYNC_BATCH_SIZE]

            # Format blocks for embedding with context
            texts = []
            uids = []
            for block in batch:
                # Get parent chain for context (skip for now to avoid rate limits)
                # parent_chain = roam.get_block_parent_chain(block["uid"])
                parent_chain = None

                formatted_text = embedding_service.format_block_for_embedding(
                    content=block["content"],
                    page_title=block.get("page_title"),
                    parent_chain=parent_chain,
                )
                texts.append(formatted_text)
                uids.append(block["uid"])

            # Generate embeddings
            embeddings = embedding_service.embed_texts(texts)

            # Store embeddings
            store.upsert_embeddings(uids, embeddings)
            total_embedded += len(uids)

            # Log progress every 10 batches or on last batch
            if batch_num % 10 == 0 or batch_num == num_batches:
                logger.info(
                    "Embedding progress: %d/%d batches (%d blocks)",
                    batch_num, num_batches, total_embedded
                )

        # Update sync timestamp to the latest edit_time
        max_edit_time = max(b["edit_time"] for b in blocks if b.get("edit_time"))
        store.set_last_sync_timestamp(max_edit_time)
        store.set_sync_status(SyncStatus.COMPLETED)

        embed_elapsed = time.time() - embed_start
        elapsed = time.time() - start_time
        sync_type = "Full" if do_full_sync else "Incremental"
        logger.info(
            "%s sync completed: %d blocks in %.1fs (embedding: %.1fs)",
            sync_type, total_embedded, elapsed, embed_elapsed
        )
        return (
            f"{sync_type} sync completed in {elapsed:.1f}s. "
            f"Processed {len(blocks)} blocks, embedded {total_embedded}."
        )

    except RoamAPIError as e:
        logger.error("Sync failed with RoamAPIError: %s", e)
        return f"Error during sync: {str(e)}"
    except Exception as e:
        logger.error("Unexpected error during sync: %s", e, exc_info=True)
        return f"Unexpected error during sync: {str(e)}"


# Constants for semantic search
SEARCH_MIN_SIMILARITY = 0.3
RECENCY_BOOST_DAYS = 30
RECENCY_BOOST_MAX = 0.1


def semantic_search(
    query: str,
    limit: int = 10,
    include_context: bool = True,
) -> str:
    """Search for blocks using semantic similarity.

    Args:
        query: Natural language search query.
        limit: Maximum number of results to return (default: 10).
        include_context: Include parent hierarchy context (default: True).

    Returns:
        Formatted search results with block content, page titles, and similarity.
    """
    search_start = time.time()
    logger.debug("Semantic search started: query='%s', limit=%d", query, limit)

    try:
        roam = get_roam_client()
        store = get_vector_store(roam.graph_name)
        embedding_service = get_embedding_service()

        # Check if index is initialized
        if store.get_sync_status() == SyncStatus.NOT_INITIALIZED:
            return (
                "Vector index not initialized. "
                "Please run sync_index first to build the search index."
            )

        # Perform incremental sync before search
        last_timestamp = store.get_last_sync_timestamp()
        if last_timestamp is not None:
            modified_blocks = roam.get_blocks_modified_since(last_timestamp)
            if modified_blocks:
                logger.info(
                    "Pre-search sync: updating %d modified blocks", len(modified_blocks)
                )
                # Sync the modified blocks
                store.upsert_blocks(modified_blocks)

                # Generate and store embeddings
                texts = []
                uids = []
                for block in modified_blocks:
                    formatted_text = embedding_service.format_block_for_embedding(
                        content=block["content"],
                        page_title=block.get("page_title"),
                        parent_chain=None,
                    )
                    texts.append(formatted_text)
                    uids.append(block["uid"])

                embeddings = embedding_service.embed_texts(texts)
                store.upsert_embeddings(uids, embeddings)

                # Update sync timestamp
                max_edit_time = max(
                    b["edit_time"] for b in modified_blocks if b.get("edit_time")
                )
                store.set_last_sync_timestamp(max_edit_time)

        # Embed the query
        query_embedding = embedding_service.embed_single(query)

        # Search the vector store (fetch more than limit to allow for filtering)
        raw_results = store.search(
            query_embedding,
            limit=limit * 2,
            min_similarity=SEARCH_MIN_SIMILARITY,
        )

        if not raw_results:
            logger.debug("No results found for query: %s", query)
            return f"No results found for: {query}"

        # Apply recency boost
        now_ms = int(time.time() * 1000)
        boosted_results = []
        for result in raw_results:
            # Get edit time from the blocks table
            cursor = store.conn.execute(
                "SELECT edit_time FROM blocks WHERE uid = ?",
                (result["uid"],),
            )
            row = cursor.fetchone()
            edit_time = row["edit_time"] if row and row["edit_time"] else 0

            # Calculate recency boost (linear decay over RECENCY_BOOST_DAYS)
            age_days = (now_ms - edit_time) / (1000 * 60 * 60 * 24)
            if age_days < RECENCY_BOOST_DAYS:
                recency_factor = 1 - (age_days / RECENCY_BOOST_DAYS)
                boost = RECENCY_BOOST_MAX * recency_factor
            else:
                boost = 0

            boosted_similarity = result["similarity"] + boost
            boosted_results.append({
                **result,
                "boosted_similarity": boosted_similarity,
                "edit_time": edit_time,
            })

        # Sort by boosted similarity and limit
        boosted_results.sort(key=lambda x: x["boosted_similarity"], reverse=True)
        final_results = boosted_results[:limit]

        # Optionally fetch parent chain context
        if include_context:
            for result in final_results:
                if not result.get("parent_chain"):
                    parent_chain = roam.get_block_parent_chain(result["uid"])
                    result["parent_chain"] = parent_chain if parent_chain else None

        # Format output
        output_lines = [f"# Search Results for: {query}\n"]
        output_lines.append(f"Found {len(final_results)} results:\n")

        for i, result in enumerate(final_results, 1):
            similarity = result["similarity"]
            page_title = result.get("page_title") or "Unknown"
            content = result["content"]

            output_lines.append(f"## {i}. [{similarity:.3f}] {page_title}")

            if include_context and result.get("parent_chain"):
                path = " > ".join(result["parent_chain"])
                output_lines.append(f"**Path:** {path}")

            # Truncate long content
            if len(content) > 500:
                content = content[:500] + "..."
            output_lines.append(f"{content}")
            output_lines.append(f"*UID: {result['uid']}*\n")

        elapsed = time.time() - search_start
        logger.info(
            "Semantic search completed: %d results in %.2fs for query='%s'",
            len(final_results), elapsed, query[:50]
        )
        return "\n".join(output_lines)

    except RoamAPIError as e:
        logger.error("Search failed with RoamAPIError: %s", e)
        return f"Error during search: {str(e)}"
    except Exception as e:
        logger.error("Unexpected error during search: %s", e, exc_info=True)
        return f"Unexpected error during search: {str(e)}"


def get_block_context(uid: str) -> str:
    """Get a block with its surrounding context.

    Args:
        uid: The UID of the block to fetch.

    Returns:
        Block content with parent chain, children, and page title.
    """
    try:
        roam = get_roam_client()

        # Get the block data
        block_data = roam.get_block(uid)

        # Get parent chain for context
        parent_chain = roam.get_block_parent_chain(uid)

        # Build output
        output_lines = ["# Block Context\n"]

        # Add page title if available
        page_title = block_data.get(":node/title")
        if page_title:
            output_lines.append(f"**Page:** {page_title}\n")

        # Add parent chain
        if parent_chain:
            path = " > ".join(parent_chain)
            output_lines.append(f"**Path:** {path}\n")

        # Add block content
        content = block_data.get(":block/string", "")
        output_lines.append(f"**Content:** {content}\n")
        output_lines.append(f"**UID:** {uid}\n")

        # Add children if present
        children = block_data.get(":block/children", [])
        if children:
            output_lines.append("\n## Children\n")
            output_lines.append(roam.process_blocks(children, 0))

        return "\n".join(output_lines)

    except BlockNotFoundError as e:
        return f"Error: {str(e)}"
    except RoamAPIError as e:
        return f"Error fetching block: {str(e)}"


def search_by_text(
    text: str, page_title: str | None = None, limit: int = 20
) -> str:
    """Search for blocks containing text (keyword search).

    Args:
        text: Text to search for (case-sensitive substring match).
        page_title: Optional page title to limit search scope.
        limit: Maximum number of results to return.

    Returns:
        Formatted search results with block content and page context.
    """
    try:
        roam = get_roam_client()
        results = roam.search_blocks_by_text(text, page_title, limit)

        if not results:
            scope = f" in page '{page_title}'" if page_title else ""
            return f"No blocks found containing '{text}'{scope}."

        output_lines = [f"# Text Search Results for: {text}\n"]
        if page_title:
            output_lines.append(f"**Scope:** {page_title}\n")
        output_lines.append(f"Found {len(results)} results:\n")

        for i, result in enumerate(results, 1):
            content = result["content"]
            result_page = result.get("page_title") or "Unknown"

            output_lines.append(f"## {i}. {result_page}")

            # Truncate long content
            if len(content) > 500:
                content = content[:500] + "..."
            output_lines.append(f"{content}")
            output_lines.append(f"*UID: {result['uid']}*\n")

        return "\n".join(output_lines)

    except InvalidQueryError as e:
        return f"Error: Invalid search text - {str(e)}"
    except RoamAPIError as e:
        return f"Error searching blocks: {str(e)}"


def raw_query(query: str, args: list | None = None) -> str:
    """Execute an arbitrary Datalog query against the Roam graph.

    Args:
        query: Datalog query string.
        args: Optional list of query arguments.

    Returns:
        JSON-formatted query results.

    Warning:
        This is a power user tool. Malformed queries may return errors.
    """
    try:
        roam = get_roam_client()
        results = roam.run_query(query, args)

        return json.dumps(results, indent=2, default=str)

    except InvalidQueryError as e:
        return f"Error: Invalid query - {str(e)}"
    except RoamAPIError as e:
        return f"Error executing query: {str(e)}"


def get_backlinks(page_title: str, limit: int = 20) -> str:
    """Get all blocks that reference a page (backlinks).

    Args:
        page_title: Title of the page to find references to.
        limit: Maximum number of results to return.

    Returns:
        Formatted list of blocks that reference the page.
    """
    try:
        roam = get_roam_client()
        results = roam.get_references_to_page(page_title, limit)

        if not results:
            return f"No blocks found referencing '{page_title}'."

        output_lines = [f"# Backlinks to: {page_title}\n"]
        output_lines.append(f"Found {len(results)} references:\n")

        for i, result in enumerate(results, 1):
            content = result.get("string", "")

            # Truncate long content
            if len(content) > 500:
                content = content[:500] + "..."
            output_lines.append(f"## {i}.")
            output_lines.append(f"{content}")
            output_lines.append(f"*UID: {result['uid']}*\n")

        return "\n".join(output_lines)

    except InvalidQueryError as e:
        return f"Error: Invalid page title - {str(e)}"
    except RoamAPIError as e:
        return f"Error fetching backlinks: {str(e)}"


# Create the server instance - this is what mcp dev looks for
server = Server("mcp-roam")


# Set up the tools
@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return list of available tools.

    Returns:
        List of Tool objects describing available MCP tools.
    """
    return [
        Tool(
            name="hello_world",
            description="Simple hello world greeting from Roam MCP server",
            inputSchema=HelloWorld.model_json_schema(),
        ),
        Tool(
            name="get_page",
            description="Retrieve a page's content in clean markdown format",
            inputSchema=GetPage.model_json_schema(),
        ),
        Tool(
            name="create_block",
            description="Add a new block to a Roam page",
            inputSchema=CreateBlock.model_json_schema(),
        ),
        Tool(
            name="daily_context",
            description="Get daily notes with their linked references for context",
            inputSchema=DailyContext.model_json_schema(),
        ),
        Tool(
            name="debug_daily_notes",
            description="Debug daily note formats and show what daily notes exist",
            inputSchema=DebugDailyNotes.model_json_schema(),
        ),
        Tool(
            name="sync_index",
            description="Build or update the vector index for semantic search",
            inputSchema=SyncIndex.model_json_schema(),
        ),
        Tool(
            name="semantic_search",
            description="Search blocks using semantic similarity",
            inputSchema=SemanticSearch.model_json_schema(),
        ),
        Tool(
            name="get_block_context",
            description="Get a block with its context (parent chain, children)",
            inputSchema=GetBlockContext.model_json_schema(),
        ),
        Tool(
            name="search_by_text",
            description="Search blocks by text (keyword/substring search)",
            inputSchema=SearchByText.model_json_schema(),
        ),
        Tool(
            name="raw_query",
            description="Execute arbitrary Datalog queries (power user tool)",
            inputSchema=RawQuery.model_json_schema(),
        ),
        Tool(
            name="get_backlinks",
            description="Get all blocks that reference a page",
            inputSchema=GetBacklinks.model_json_schema(),
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls.

    Args:
        name: The name of the tool to call.
        arguments: The arguments to pass to the tool.

    Returns:
        List of TextContent objects with the tool result.

    Raises:
        ValueError: If the tool name is unknown.
    """
    match name:
        case "hello_world":
            result = hello_world(arguments.get("name", "World"))
        case "get_page":
            result = get_page(arguments["title"])
        case "create_block":
            result = create_block(
                arguments["content"],
                arguments.get("page_uid"),
                arguments.get("title")
            )
        case "daily_context":
            result = daily_context(
                arguments.get("days", 10),
                arguments.get("max_references", 10)
            )
        case "debug_daily_notes":
            result = debug_daily_notes()
        case "sync_index":
            result = sync_index(arguments.get("full", False))
        case "semantic_search":
            result = semantic_search(
                arguments["query"],
                arguments.get("limit", 10),
                arguments.get("include_context", True),
            )
        case "get_block_context":
            result = get_block_context(arguments["uid"])
        case "search_by_text":
            result = search_by_text(
                arguments["text"],
                arguments.get("page_title"),
                arguments.get("limit", 20),
            )
        case "raw_query":
            result = raw_query(
                arguments["query"],
                arguments.get("args"),
            )
        case "get_backlinks":
            result = get_backlinks(
                arguments["page_title"],
                arguments.get("limit", 20),
            )
        case _:
            raise ValueError(f"Unknown tool: {name}")

    return [TextContent(type="text", text=str(result))]


async def serve() -> None:
    """Initialize and run the MCP server.

    This is the main entry point for running the server via stdio transport.
    """
    # Initialize and run the server
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)

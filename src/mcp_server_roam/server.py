"""MCP server implementation for Roam Research API."""

import json
import logging
import re
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv

if TYPE_CHECKING:
    from mcp_server_roam.embedding import EmbeddingService
    from mcp_server_roam.vector_store import VectorStore

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel

from mcp_server_roam.embedding import get_embedding_service
from mcp_server_roam.roam_api import (
    BlockNotFoundError,
    InvalidQueryError,
    PageNotFoundError,
    RoamAPI,
    RoamAPIError,
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
class GetPage(BaseModel):
    """Input schema for get_page_markdown tool."""

    title: str
    include_backlinks: bool = True
    max_backlinks: int = 10


class CreateBlock(BaseModel):
    """Input schema for create_block tool."""

    content: str
    page_uid: str | None = None
    title: str | None = None


class DailyContext(BaseModel):
    """Input schema for context tool."""

    days: int = 10
    max_references: int = 10


class SyncIndex(BaseModel):
    """Input schema for sync_index tool."""

    full: bool = False


class SemanticSearch(BaseModel):
    """Input schema for semantic_search tool."""

    query: str
    limit: int = 10
    include_context: bool = True
    include_children: bool = False
    children_limit: int = 3
    include_backlink_count: bool = False
    include_siblings: bool = False
    sibling_count: int = 1


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
    args: list[Any] | None = None


class GetBacklinks(BaseModel):
    """Input schema for get_backlinks tool."""

    page_title: str
    limit: int = 20


# Tool implementation functions
def get_page(
    title: str, include_backlinks: bool = True, max_backlinks: int = 10
) -> str:
    """Retrieve a page's content in clean markdown format.

    This uses the Roam API to fetch the page content and converts it to a well-formatted
    markdown representation, suitable for display or further processing.

    Args:
        title: Title of the page to fetch
        include_backlinks: If True, append backlinks section showing blocks that
            reference this page
        max_backlinks: Maximum number of backlinks to include (default: 10)

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

        # Add backlinks section if requested
        if include_backlinks:
            backlinks = roam.get_references_to_page(title, max_backlinks)
            if backlinks:
                markdown += "\n---\n\n## Backlinks\n\n"
                for ref in backlinks:
                    content = ref.get("string", "")
                    if len(content) > 200:
                        content = content[:200] + "..."
                    markdown += f"- {content}\n"
                    markdown += f"  *UID: {ref['uid']}*\n"

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
            blocks = roam.get_blocks_for_sync()
            logger.info(
                "Fetched %d blocks from Roam API in %.1fs",
                len(blocks),
                time.time() - fetch_start,
            )
        else:
            # Incremental sync - get blocks modified since last sync
            last_timestamp = store.get_last_sync_timestamp()
            if last_timestamp is None:
                # No previous sync, do full
                logger.info("No previous sync found - performing full sync")
                store.set_sync_status(SyncStatus.IN_PROGRESS)
                fetch_start = time.time()
                blocks = roam.get_blocks_for_sync()
                logger.info(
                    "Fetched %d blocks from Roam API in %.1fs",
                    len(blocks),
                    time.time() - fetch_start,
                )
            else:
                store.set_sync_status(SyncStatus.IN_PROGRESS)
                logger.debug("Incremental sync from timestamp %d", last_timestamp)
                blocks = roam.get_blocks_for_sync(since_timestamp=last_timestamp)
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
            batch = blocks[i : i + SYNC_BATCH_SIZE]

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
                    batch_num,
                    num_batches,
                    total_embedded,
                )

        # Update sync timestamp to the latest edit_time
        edit_times = [b["edit_time"] for b in blocks if b.get("edit_time")]
        if edit_times:
            store.set_last_sync_timestamp(max(edit_times))
        store.set_sync_status(SyncStatus.COMPLETED)

        embed_elapsed = time.time() - embed_start
        elapsed = time.time() - start_time
        sync_type = "Full" if do_full_sync else "Incremental"
        logger.info(
            "%s sync completed: %d blocks in %.1fs (embedding: %.1fs)",
            sync_type,
            total_embedded,
            elapsed,
            embed_elapsed,
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


def _incremental_sync(
    roam: RoamAPI,
    store: "VectorStore",
    embedding_service: "EmbeddingService",
) -> int:
    """Perform incremental sync of modified blocks.

    Args:
        roam: RoamAPI client instance.
        store: VectorStore instance.
        embedding_service: EmbeddingService instance.

    Returns:
        Number of blocks synced.
    """
    last_timestamp = store.get_last_sync_timestamp()
    if last_timestamp is None:
        return 0

    modified_blocks = roam.get_blocks_for_sync(since_timestamp=last_timestamp)
    if not modified_blocks:
        return 0

    logger.info("Incremental sync: updating %d modified blocks", len(modified_blocks))

    # Store block metadata
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
    edit_times = [b["edit_time"] for b in modified_blocks if b.get("edit_time")]
    if edit_times:
        store.set_last_sync_timestamp(max(edit_times))

    return len(modified_blocks)


def calculate_recency_boost(edit_time_ms: int, now_ms: int) -> float:
    """Calculate recency boost for search results.

    Args:
        edit_time_ms: Edit time in milliseconds since epoch.
        now_ms: Current time in milliseconds since epoch.

    Returns:
        Boost value between 0 and RECENCY_BOOST_MAX.
    """
    age_days = (now_ms - edit_time_ms) / (1000 * 60 * 60 * 24)
    if age_days < RECENCY_BOOST_DAYS:
        return RECENCY_BOOST_MAX * (1 - age_days / RECENCY_BOOST_DAYS)
    return 0.0


def extract_references(content: str) -> dict[str, list[str]]:
    """Extract tags and page references from block content.

    Args:
        content: Block content string.

    Returns:
        Dict with 'tags' (list of #hashtags) and 'page_refs' (list of [[Page]] refs).
    """
    # Extract #hashtags (word characters after #, not inside [[]])
    tags = re.findall(r"(?<!\[\[)#([\w-]+)", content)

    # Extract [[Page Name]] references
    page_refs = re.findall(r"\[\[([^\]]+)\]\]", content)

    return {"tags": list(set(tags)), "page_refs": list(set(page_refs))}


def format_edit_time(edit_time_ms: int) -> str:
    """Format edit timestamp as human-readable date.

    Args:
        edit_time_ms: Edit time in milliseconds since epoch.

    Returns:
        Formatted date string (e.g., "Dec 15, 2025").
    """
    if not edit_time_ms:
        return "Unknown"
    dt = datetime.fromtimestamp(edit_time_ms / 1000)
    return dt.strftime("%b %d, %Y")


def semantic_search(
    query: str,
    limit: int = 10,
    include_context: bool = True,
    include_children: bool = False,
    children_limit: int = 3,
    include_backlink_count: bool = False,
    include_siblings: bool = False,
    sibling_count: int = 1,
) -> str:
    """Search for blocks using semantic similarity.

    Args:
        query: Natural language search query.
        limit: Maximum number of results to return (default: 10).
        include_context: Include parent hierarchy context (default: True).
        include_children: Include preview of child blocks (default: False).
        children_limit: Max number of children to show (default: 3).
        include_backlink_count: Show count of blocks referencing each result.
        include_siblings: Include previous/next sibling blocks (default: False).
        sibling_count: Number of siblings before/after to show (default: 1).

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
        _incremental_sync(roam, store, embedding_service)

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
            edit_time = result.get("edit_time", 0)
            boost = calculate_recency_boost(edit_time, now_ms)
            boosted_similarity = result["similarity"] + boost
            boosted_results.append(
                {
                    **result,
                    "boosted_similarity": boosted_similarity,
                    "edit_time": edit_time,
                }
            )

        # Sort by boosted similarity and limit
        boosted_results.sort(key=lambda x: x["boosted_similarity"], reverse=True)
        final_results = boosted_results[:limit]

        # Fetch additional context for each result
        for result in final_results:
            uid = result["uid"]

            # Parent chain context
            if include_context and not result.get("parent_chain"):
                parent_chain = roam.get_block_parent_chain(uid)
                result["parent_chain"] = parent_chain if parent_chain else None

            # Children preview (Phase 1)
            if include_children:
                result["children"] = roam.get_block_children_preview(
                    uid, children_limit
                )

            # Backlink count (Phase 4)
            if include_backlink_count:
                result["backlink_count"] = roam.get_block_reference_count(uid)

            # Siblings context (Phase 5)
            if include_siblings:
                result["siblings"] = roam.get_block_siblings(uid, sibling_count)

        # Format output
        output_lines = [f"# Search Results for: {query}\n"]
        output_lines.append(f"Found {len(final_results)} results:\n")

        for i, result in enumerate(final_results, 1):
            similarity = result["similarity"]
            page_title = result.get("page_title") or "Unknown"
            content = result["content"]
            edit_time = result.get("edit_time", 0)

            output_lines.append(f"## {i}. [{similarity:.3f}] {page_title}")

            # Path context
            if include_context and result.get("parent_chain"):
                path = " > ".join(result["parent_chain"])
                output_lines.append(f"**Path:** {path}")

            # Metadata line: Modified date and backlink count (Phases 3 & 4)
            metadata_parts = []
            metadata_parts.append(f"**Modified:** {format_edit_time(edit_time)}")
            if include_backlink_count:
                count = result.get("backlink_count", 0)
                metadata_parts.append(f"**Referenced by:** {count} blocks")
            output_lines.append(" | ".join(metadata_parts))

            # Tags and page references (Phase 2)
            refs = extract_references(content)
            if refs["tags"]:
                output_lines.append(
                    f"**Tags:** {', '.join('#' + t for t in refs['tags'])}"
                )
            if refs["page_refs"]:
                links = ", ".join("[[" + p + "]]" for p in refs["page_refs"])
                output_lines.append(f"**Links:** {links}")

            # Sibling context (Phase 5)
            if include_siblings and result.get("siblings"):
                siblings = result["siblings"]
                if siblings["before"] or siblings["after"]:
                    output_lines.append("\n**Context:**")
                    for sib in siblings["before"]:
                        sib_content = (
                            sib["content"][:100] + "..."
                            if len(sib["content"]) > 100
                            else sib["content"]
                        )
                        output_lines.append(f"  ↑ {sib_content}")
                    # Current block indicator
                    display_content = (
                        content[:100] + "..." if len(content) > 100 else content
                    )
                    output_lines.append(f"  → **{display_content}**")
                    for sib in siblings["after"]:
                        sib_content = (
                            sib["content"][:100] + "..."
                            if len(sib["content"]) > 100
                            else sib["content"]
                        )
                        output_lines.append(f"  ↓ {sib_content}")
                    output_lines.append("")

            # Main content (if not already shown in siblings context)
            if not (
                include_siblings
                and result.get("siblings")
                and (result["siblings"]["before"] or result["siblings"]["after"])
            ):
                # Truncate long content
                if len(content) > 500:
                    content = content[:500] + "..."
                output_lines.append(f"\n{content}")

            # Children preview (Phase 1)
            if include_children and result.get("children"):
                output_lines.append("\n**Children:**")
                for child in result["children"]:
                    child_content = child["content"]
                    if len(child_content) > 150:
                        child_content = child_content[:150] + "..."
                    output_lines.append(f"  - {child_content}")

            output_lines.append(f"\n*UID: {result['uid']}*\n")

        elapsed = time.time() - search_start
        logger.info(
            "Semantic search completed: %d results in %.2fs for query='%s'",
            len(final_results),
            elapsed,
            query[:50],
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


def search_by_text(text: str, page_title: str | None = None, limit: int = 20) -> str:
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


def raw_query(query: str, args: list[Any] | None = None) -> str:
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
            name="get_page",
            description=(
                "Retrieve a page's content in clean markdown format. "
                "Optionally include backlinks (blocks that reference this page)."
            ),
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
            name="sync_index",
            description="Build or update the vector index for semantic search",
            inputSchema=SyncIndex.model_json_schema(),
        ),
        Tool(
            name="semantic_search",
            description=(
                "Search blocks using semantic similarity. "
                "Returns results with tags, page links, and edit dates. "
                "Optional: include_children for nested content, "
                "include_backlink_count for reference counts, "
                "include_siblings for surrounding context."
            ),
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
        case "get_page":
            result = get_page(
                arguments["title"],
                arguments.get("include_backlinks", True),
                arguments.get("max_backlinks", 10),
            )
        case "create_block":
            result = create_block(
                arguments["content"], arguments.get("page_uid"), arguments.get("title")
            )
        case "daily_context":
            result = daily_context(
                arguments.get("days", 10), arguments.get("max_references", 10)
            )
        case "sync_index":
            result = sync_index(arguments.get("full", False))
        case "semantic_search":
            result = semantic_search(
                arguments["query"],
                arguments.get("limit", 10),
                arguments.get("include_context", True),
                arguments.get("include_children", False),
                arguments.get("children_limit", 3),
                arguments.get("include_backlink_count", False),
                arguments.get("include_siblings", False),
                arguments.get("sibling_count", 1),
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

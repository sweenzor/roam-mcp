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


class QuickCaptureEnrich(BaseModel):
    """Input schema for quick_capture_enrich tool."""

    note: str


class QuickCaptureCommit(BaseModel):
    """Input schema for quick_capture_commit tool."""

    note: str


# Minimum page name length to match (avoid false positives)
MIN_PAGE_NAME_LENGTH = 3

# Default tab expansion width (tabs become this many spaces)
DEFAULT_TAB_WIDTH = 2


def detect_indent_unit(lines: list[str]) -> int:
    """Detect the indentation unit (spaces per level).

    Strategy:
    1. Find all indentation levels used
    2. Calculate GCD of all indent amounts
    3. Default to 2 if can't determine

    Args:
        lines: List of lines to analyze.

    Returns:
        The detected indent unit (number of spaces per level).
    """
    from functools import reduce
    from math import gcd

    indents: set[int] = set()
    for line in lines:
        if line.strip():
            # Expand tabs to spaces for counting
            expanded = line.expandtabs(DEFAULT_TAB_WIDTH)
            stripped = expanded.lstrip()
            indent = len(expanded) - len(stripped)
            if indent > 0:
                indents.add(indent)

    if not indents:
        return DEFAULT_TAB_WIDTH

    # Find GCD of all indents
    return reduce(gcd, indents) or DEFAULT_TAB_WIDTH


def parse_note_to_blocks(note: str) -> list[dict[str, Any]]:
    """Parse any multi-line note format into a block tree.

    Supports:
    - Different indentation styles (2-space, 4-space, tabs)
    - Optional bullet markers (-, *, •, ‣ or none)
    - Mixed indentation (normalizes using GCD)

    Args:
        note: Multi-line note string.

    Returns:
        List of block dicts with 'content' and optional 'children' keys.
        Single-line notes return a list with one block (no children).
    """
    lines = note.split("\n")

    # Filter out empty lines
    non_empty_lines = [line for line in lines if line.strip()]

    if not non_empty_lines:
        return []

    # Single line case - return simple block
    if len(non_empty_lines) == 1:
        content = non_empty_lines[0].strip()
        # Remove bullet prefix if present
        for prefix in ["- ", "* ", "• ", "‣ "]:
            if content.startswith(prefix):
                content = content[len(prefix) :]
                break
        return [{"content": content}]

    # Detect indent unit
    indent_unit = detect_indent_unit(non_empty_lines)

    # Parse into block tree
    root_blocks: list[dict[str, Any]] = []
    # Stack: (children list, level)
    stack: list[tuple[list[dict[str, Any]], int]] = [(root_blocks, -1)]

    for line in lines:
        if not line.strip():
            continue

        # Expand tabs and calculate level
        expanded = line.expandtabs(indent_unit)
        stripped = expanded.lstrip()
        indent = len(expanded) - len(stripped)
        level = indent // indent_unit if indent_unit > 0 else 0

        # Remove optional bullet prefix
        content = stripped
        for prefix in ["- ", "* ", "• ", "‣ "]:
            if content.startswith(prefix):
                content = content[len(prefix) :]
                break

        block: dict[str, Any] = {"content": content, "children": []}

        # Find correct parent (pop until we find a parent with lower level)
        while len(stack) > 1 and stack[-1][1] >= level:
            stack.pop()

        # Add to parent's children list
        parent_list = stack[-1][0]
        parent_list.append(block)

        # Push this block's children list onto stack
        stack.append((block["children"], level))

    # Clean up empty children lists
    def clean_empty_children(blocks: list[dict[str, Any]]) -> None:
        for block in blocks:
            if block.get("children"):
                clean_empty_children(block["children"])
            else:
                block.pop("children", None)

    clean_empty_children(root_blocks)

    return root_blocks


def format_blocks_preview(blocks: list[dict[str, Any]], depth: int = 0) -> str:
    """Format blocks as a tree preview for display.

    Args:
        blocks: List of block dicts with 'content' and optional 'children'.
        depth: Current nesting depth (0 = root).

    Returns:
        Tree-formatted string showing block hierarchy.
    """
    lines: list[str] = []

    for i, block in enumerate(blocks):
        content = block["content"]
        children = block.get("children", [])
        is_last = i == len(blocks) - 1

        if depth == 0:
            # Root level - no prefix
            lines.append(content)
        else:
            # Use tree characters for nested levels
            prefix = "  " * (depth - 1)
            connector = "└── " if is_last else "├── "
            lines.append(prefix + connector + content)

        # Process children
        if children:
            child_preview = format_blocks_preview(children, depth + 1)
            lines.append(child_preview)

    return "\n".join(lines)


def count_blocks(blocks: list[dict[str, Any]]) -> int:
    """Count total number of blocks including nested children.

    Args:
        blocks: List of block dicts with optional 'children'.

    Returns:
        Total block count.
    """
    count = len(blocks)
    for block in blocks:
        if block.get("children"):
            count += count_blocks(block["children"])
    return count


def is_multiline_note(note: str) -> bool:
    """Check if a note contains multiple non-empty lines.

    Args:
        note: The note text.

    Returns:
        True if the note has multiple non-empty lines.
    """
    non_empty_lines = [line for line in note.split("\n") if line.strip()]
    return len(non_empty_lines) > 1


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


def enrich_note_with_links(note: str, page_titles: list[str]) -> dict[str, Any]:
    """Enrich a note by adding [[page links]] for matching page names.

    Matches are case-insensitive but preserve the original case from the graph.
    Longer page names are matched first to avoid partial matches.
    Only matches whole words/phrases (not substrings within words).

    Performance: Uses word-based pre-filtering to avoid regex matching against
    pages that can't possibly match, reducing O(pages) to O(candidate_pages).

    Args:
        note: The raw note text to enrich.
        page_titles: List of all page titles from the graph.

    Returns:
        Dict with 'enriched_note' and 'matches_found' list.
    """
    # Filter pages by minimum length and sort by length descending
    filtered_pages = [p for p in page_titles if len(p) >= MIN_PAGE_NAME_LENGTH]

    # Pre-filter optimization: extract words from note for fast candidate filtering
    # A page can only match if all its words appear in the note
    note_lower = note.lower()
    note_words = set(re.findall(r"\w+", note_lower))

    # Filter to only pages where all words appear in the note
    candidate_pages = []
    for page in filtered_pages:
        page_words = re.findall(r"\w+", page.lower())
        if page_words and all(word in note_words for word in page_words):
            candidate_pages.append(page)

    # Sort candidates by length descending (longer matches first)
    sorted_pages = sorted(candidate_pages, key=len, reverse=True)

    # Track which positions are already linked (to avoid double-linking)
    linked_positions: set[tuple[int, int]] = set()

    # Find existing links in the note and mark their positions
    existing_links = list(re.finditer(r"\[\[([^\]]+)\]\]", note))
    for match in existing_links:
        linked_positions.add((match.start(), match.end()))

    # Also find existing #tags
    existing_tags = list(re.finditer(r"#([\w-]+)", note))
    for match in existing_tags:
        linked_positions.add((match.start(), match.end()))

    matches_found: list[str] = []
    replacements: list[tuple[int, int, str]] = []  # (start, end, page)

    for page in sorted_pages:
        # Skip if this page is already linked in the note (case-insensitive check)
        # This avoids creating duplicate links for the same page
        if re.search(rf"\[\[{re.escape(page)}\]\]", note, re.IGNORECASE):
            continue

        # Escape special regex characters in page name
        escaped_page = re.escape(page)

        # Build a pattern that works with word boundaries
        # For page names that start/end with non-word chars, use lookarounds
        first_char = page[0] if page else ""
        last_char = page[-1] if page else ""

        # Check if first/last chars are word characters
        first_is_word = bool(re.match(r"\w", first_char))
        last_is_word = bool(re.match(r"\w", last_char))

        # Build appropriate boundary patterns
        # Use \b for word chars, lookaround for non-word chars
        start_boundary = r"\b" if first_is_word else r"(?<!\w)"
        end_boundary = r"\b" if last_is_word else r"(?!\w)"

        pattern = rf"{start_boundary}{escaped_page}{end_boundary}"

        for match in re.finditer(pattern, note, re.IGNORECASE):
            start, end = match.start(), match.end()

            # Check if this position overlaps with any existing link
            overlaps = False
            for linked_start, linked_end in linked_positions:
                if start < linked_end and end > linked_start:
                    overlaps = True
                    break

            if not overlaps:
                # Store the replacement (use the canonical page title)
                replacements.append((start, end, page))
                linked_positions.add((start, end))
                if page not in matches_found:
                    matches_found.append(page)

    # Apply replacements from end to start to preserve positions
    replacements.sort(key=lambda x: x[0], reverse=True)
    enriched = note
    for start, end, page in replacements:
        enriched = enriched[:start] + f"[[{page}]]" + enriched[end:]

    return {"enriched_note": enriched, "matches_found": matches_found}


def enrich_blocks(
    blocks: list[dict[str, Any]], page_titles: list[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Enrich block contents with page links.

    Args:
        blocks: List of block dicts with 'content' and optional 'children'.
        page_titles: List of all page titles from the graph.

    Returns:
        Tuple of (enriched_blocks, all_matches_found).
    """
    all_matches: list[str] = []
    enriched: list[dict[str, Any]] = []

    for block in blocks:
        result = enrich_note_with_links(block["content"], page_titles)
        enriched_block: dict[str, Any] = {"content": result["enriched_note"]}

        for match in result["matches_found"]:
            if match not in all_matches:
                all_matches.append(match)

        if block.get("children"):
            enriched_children, child_matches = enrich_blocks(
                block["children"], page_titles
            )
            enriched_block["children"] = enriched_children
            for match in child_matches:
                if match not in all_matches:
                    all_matches.append(match)

        enriched.append(enriched_block)

    return enriched, all_matches


def quick_capture_enrich(note: str) -> str:
    """Enrich a note with page links based on existing pages in the graph.

    Supports both single-line and multi-line notes. Multi-line notes with
    indentation are parsed into a block hierarchy.

    Args:
        note: The raw note text to enrich.

    Returns:
        JSON string with enriched_note, matches_found, daily_note_title,
        and for multi-line notes: block_count and preview.
    """
    try:
        roam = get_roam_client()

        # Get all page titles
        page_titles = roam.get_all_page_titles()
        logger.info("Fetched %d page titles for enrichment", len(page_titles))

        # Get today's daily note title
        daily_note_title = roam.get_todays_daily_note_title()

        # Check if multi-line
        if is_multiline_note(note):
            # Parse into blocks
            blocks = parse_note_to_blocks(note)
            block_count = count_blocks(blocks)

            # Enrich each block
            enriched_blocks, matches_found = enrich_blocks(blocks, page_titles)

            # Generate preview
            preview = format_blocks_preview(enriched_blocks)

            # Reconstruct enriched note text (preserving original structure)
            enriched_result = enrich_note_with_links(note, page_titles)

            return json.dumps(
                {
                    "enriched_note": enriched_result["enriched_note"],
                    "matches_found": matches_found,
                    "daily_note_title": daily_note_title,
                    "original_note": note,
                    "block_count": block_count,
                    "preview": preview,
                    "is_multiline": True,
                },
                indent=2,
            )
        else:
            # Single-line case - original behavior
            result = enrich_note_with_links(note, page_titles)

            return json.dumps(
                {
                    "enriched_note": result["enriched_note"],
                    "matches_found": result["matches_found"],
                    "daily_note_title": daily_note_title,
                    "original_note": note,
                    "is_multiline": False,
                },
                indent=2,
            )

    except RoamAPIError as e:
        return json.dumps({"error": f"Error enriching note: {str(e)}"})


def quick_capture_commit(note: str) -> str:
    """Append a note to today's daily note page.

    Supports both single-line and multi-line notes. Multi-line notes with
    indentation are parsed into nested blocks.

    Args:
        note: The note text to append (can be enriched or plain).

    Returns:
        Confirmation message with daily note title, block count, and root UID.
    """
    try:
        roam = get_roam_client()

        # Check if multi-line
        if is_multiline_note(note):
            # Parse into blocks
            blocks = parse_note_to_blocks(note)

            # Use batch write for multi-block creation
            result = roam.append_blocks_to_daily_note(blocks)

            block_count = result["block_count"]
            daily_title = result["daily_note_title"]
            return (
                f"Added {block_count} blocks to {daily_title}\n"
                f"Root block UID: {result['root_uid']}"
            )
        else:
            # Single-line case - original behavior
            result = roam.append_block_to_daily_note(note)

            return (
                f"Added to {result['daily_note_title']}\n"
                f"Block UID: {result['block_uid']}"
            )

    except PageNotFoundError as e:
        return f"Error: {str(e)}"
    except RoamAPIError as e:
        return f"Error adding note: {str(e)}"


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
        Tool(
            name="quick_capture_enrich",
            description=(
                "Enrich a quick note with [[page links]] and #tags based on "
                "existing pages in your Roam graph. Returns the enriched note "
                "for review before committing."
            ),
            inputSchema=QuickCaptureEnrich.model_json_schema(),
        ),
        Tool(
            name="quick_capture_commit",
            description=(
                "Append a note to today's daily note page. "
                "Use after reviewing the enriched note from quick_capture_enrich."
            ),
            inputSchema=QuickCaptureCommit.model_json_schema(),
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
        case "quick_capture_enrich":
            result = quick_capture_enrich(arguments["note"])
        case "quick_capture_commit":
            result = quick_capture_commit(arguments["note"])
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

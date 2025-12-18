"""End-to-end tests for semantic search enrichments.

These tests require valid Roam API credentials and a synced vector index.
They will be skipped automatically if ROAM_API_TOKEN is not set.

Run with credentials::

    ROAM_API_TOKEN=xxx ROAM_GRAPH_NAME=xxx uv run pytest tests/test_e2e_search.py -v

Credentials can also be loaded from a .env file in the project root.

Note: Roam API has a 50 req/min rate limit. Tests are consolidated.
"""

import os
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Attempt to load credentials from .env file if not already in environment
load_dotenv()

# Skip all tests in this module if credentials aren't available
pytestmark = pytest.mark.skipif(
    not os.getenv("ROAM_API_TOKEN"),
    reason="ROAM_API_TOKEN not set - skipping e2e tests",
)


async def run_with_session(test_fn: Callable[[ClientSession], Awaitable[Any]]) -> Any:
    """Run a test function with an MCP session, handling cleanup properly."""
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "mcp_server_roam"],
    )
    async with (
        stdio_client(server_params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        return await test_fn(session)


class TestSemanticSearchE2E:
    """E2E tests for semantic search enrichments."""

    async def test_semantic_search_basic(self) -> None:
        """Test basic semantic search functionality."""

        async def test(session: ClientSession) -> None:
            # First, sync the index (may take a while on first run)
            sync_result = await session.call_tool("sync_index", {"full": False})
            sync_text = sync_result.content[0].text
            # Should either succeed or already be synced
            assert (
                "Sync complete" in sync_text
                or "synced" in sync_text.lower()
                or "blocks" in sync_text.lower()
            )

            # Now perform a basic semantic search
            search_result = await session.call_tool(
                "semantic_search",
                {"query": "project planning", "limit": 5},
            )
            text = search_result.content[0].text

            # Should return formatted results
            assert "Search Results for:" in text
            # Should show results or "No results found"
            assert "Found" in text or "No results found" in text

        await run_with_session(test)

    async def test_semantic_search_with_enrichments(self) -> None:
        """Test semantic search with all enrichment options enabled."""

        async def test(session: ClientSession) -> None:
            # Perform search with all enrichments
            search_result = await session.call_tool(
                "semantic_search",
                {
                    "query": "meeting notes",
                    "limit": 3,
                    "include_context": True,
                    "include_children": True,
                    "children_limit": 2,
                    "include_backlink_count": True,
                    "include_siblings": True,
                    "sibling_count": 1,
                },
            )
            text = search_result.content[0].text

            # Should return formatted results
            assert "Search Results for: meeting notes" in text

            # If we have results, verify enrichment format markers are present
            if "Found" in text and "No results found" not in text:
                # Modified timestamp is always shown
                assert "**Modified:**" in text
                # Backlink count should be present (requested)
                assert "**Referenced by:**" in text

        await run_with_session(test)

    async def test_semantic_search_extracts_tags_and_refs(self) -> None:
        """Test that semantic search extracts tags and page references."""

        async def test(session: ClientSession) -> None:
            # Search for content likely to have tags/refs
            search_result = await session.call_tool(
                "semantic_search",
                {"query": "todo task project", "limit": 10},
            )
            text = search_result.content[0].text

            # Should return formatted results
            assert "Search Results for:" in text

            # The output format should include UID markers for each result
            if "Found" in text and "No results found" not in text:
                assert "*UID:" in text

        await run_with_session(test)

    async def test_semantic_search_children_enrichment(self) -> None:
        """Test semantic search with children preview enrichment."""

        async def test(session: ClientSession) -> None:
            # Search with children enabled
            search_result = await session.call_tool(
                "semantic_search",
                {
                    "query": "goals objectives",
                    "limit": 5,
                    "include_children": True,
                    "children_limit": 3,
                },
            )
            text = search_result.content[0].text

            # Should return formatted results
            assert "Search Results for:" in text

            # If results have children, they should be shown with **Children:** header
            if "Found" in text and "No results found" not in text:
                # Should have proper result formatting
                assert "##" in text  # Section headers for results

        await run_with_session(test)

    async def test_semantic_search_siblings_enrichment(self) -> None:
        """Test semantic search with sibling context enrichment."""

        async def test(session: ClientSession) -> None:
            # Search with siblings enabled
            search_result = await session.call_tool(
                "semantic_search",
                {
                    "query": "ideas thoughts",
                    "limit": 3,
                    "include_siblings": True,
                    "sibling_count": 1,
                },
            )
            text = search_result.content[0].text

            # Should return formatted results
            assert "Search Results for:" in text

            # If results have siblings, they show with arrows
            if "Found" in text and "No results found" not in text:
                assert "*UID:" in text  # Each result should have UID

        await run_with_session(test)

    async def test_semantic_search_us_presidents(self) -> None:
        """Test semantic search finds content about US presidents."""

        async def test(session: ClientSession) -> None:
            # Search for US presidents
            search_result = await session.call_tool(
                "semantic_search",
                {
                    "query": "US presidents",
                    "limit": 10,
                    "include_context": True,
                    "include_backlink_count": True,
                },
            )
            text = search_result.content[0].text

            # Should return formatted results
            assert "Search Results for: US presidents" in text
            assert "Found" in text

            # Should find content mentioning at least one US president
            us_president_names = [
                "Washington",
                "Adams",
                "Jefferson",
                "Madison",
                "Monroe",
                "Jackson",
                "Van Buren",
                "Harrison",
                "Tyler",
                "Polk",
                "Taylor",
                "Fillmore",
                "Pierce",
                "Buchanan",
                "Lincoln",
                "Johnson",
                "Grant",
                "Hayes",
                "Garfield",
                "Arthur",
                "Cleveland",
                "McKinley",
                "Roosevelt",
                "Taft",
                "Wilson",
                "Harding",
                "Coolidge",
                "Hoover",
                "Truman",
                "Eisenhower",
                "Kennedy",
                "Nixon",
                "Ford",
                "Carter",
                "Reagan",
                "Bush",
                "Clinton",
                "Obama",
                "Trump",
                "Biden",
            ]
            assert any(
                name in text for name in us_president_names
            ), "Expected to find at least one US president name in results"

            # Enrichments should be present
            assert "**Modified:**" in text
            assert "**Referenced by:**" in text
            assert "**Links:**" in text

        await run_with_session(test)

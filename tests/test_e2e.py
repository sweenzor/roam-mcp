"""End-to-end tests for the Roam MCP server.

These tests require valid Roam API credentials and will be skipped
automatically if ROAM_API_TOKEN is not set in the environment.

Run with credentials::

    ROAM_API_TOKEN=xxx ROAM_GRAPH_NAME=xxx uv run pytest tests/test_e2e.py -v

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


class TestE2E:
    """E2E tests consolidated to minimize API calls (50 req/min limit)."""

    async def test_server_tools(self) -> None:
        """Test server lists all expected tools."""

        async def test(session: ClientSession) -> None:
            # Check tools are registered
            tools = await session.list_tools()
            tool_names = {t.name for t in tools.tools}
            expected = {
                "get_page",
                "create_block",
                "daily_context",
                "sync_index",
                "semantic_search",
                "get_block_context",
                "search_by_text",
                "raw_query",
                "get_backlinks",
            }
            assert expected == tool_names

        await run_with_session(test)

    async def test_page_not_found(self) -> None:
        """Test fetching a page that doesn't exist returns error."""

        async def test(session: ClientSession) -> None:
            result = await session.call_tool(
                "get_page", {"title": "This Page Should Not Exist 12345xyz"}
            )
            text = result.content[0].text
            assert "Error" in text or "not found" in text.lower()

        await run_with_session(test)

    async def test_daily_notes_context(self) -> None:
        """Test daily note context retrieval."""

        async def test(session: ClientSession) -> None:
            # Test daily_context (fetches 1 day only to minimize API calls)
            context_result = await session.call_tool(
                "daily_context", {"days": 1, "max_references": 3}
            )
            assert "Daily Notes Context" in context_result.content[0].text

        await run_with_session(test)

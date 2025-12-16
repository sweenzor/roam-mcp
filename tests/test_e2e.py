"""End-to-end tests for the Roam MCP server.

These tests require valid Roam API credentials and will be skipped
automatically if ROAM_API_TOKEN is not set in the environment.

Run with credentials::

    ROAM_API_TOKEN=xxx ROAM_GRAPH_NAME=xxx uv run pytest tests/test_e2e.py -v

Credentials can also be loaded from a .env file in the project root.

Note: Roam API has a 50 req/min rate limit. Tests are consolidated.
"""

import os
import re
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

    async def test_server_tools_and_hello(self) -> None:
        """Test server lists tools and hello_world works."""

        async def test(session: ClientSession) -> None:
            # Check tools are registered
            tools = await session.list_tools()
            tool_names = {t.name for t in tools.tools}
            expected = {
                "hello_world",
                "get_page",
                "create_block",
                "daily_context",
                "debug_daily_notes",
                "sync_index",
                "semantic_search",
                "get_block_context",
                "search_by_text",
                "raw_query",
                "get_backlinks",
            }
            assert expected == tool_names

            # Test hello_world
            result = await session.call_tool("hello_world", {"name": "E2E"})
            assert "Hello, E2E!" in result.content[0].text

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

    async def test_daily_notes_and_context(self) -> None:
        """Test daily note detection and context retrieval."""

        async def test(session: ClientSession) -> None:
            # Test debug_daily_notes (detects format)
            debug_result = await session.call_tool("debug_daily_notes", {})
            debug_text = debug_result.content[0].text
            assert "Daily Notes Debug" in debug_text
            assert "Detected format" in debug_text

            # Test daily_context (uses cached format, fetches 1 day only)
            context_result = await session.call_tool(
                "daily_context", {"days": 1, "max_references": 3}
            )
            assert "Daily Notes Context" in context_result.content[0].text

            # If a daily note was found, try to fetch it
            for line in debug_text.split("\n"):
                if line.startswith("✅"):
                    match = re.search(r"\*\*(.+?)\*\*", line)
                    if match:
                        date_str = match.group(1)
                        result = await session.call_tool(
                            "get_page", {"title": date_str}
                        )
                        assert date_str in result.content[0].text
                        return

        await run_with_session(test)

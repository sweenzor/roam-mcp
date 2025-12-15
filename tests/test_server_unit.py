"""Unit tests for the Roam MCP server with mocked dependencies.

These tests use pytest-mock to mock external dependencies (RoamAPI) and ensure
fast, isolated testing without requiring actual Roam API access.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from mcp_server_roam.roam_api import (
    AuthenticationError,
    InvalidQueryError,
    PageNotFoundError,
    RoamAPIError,
)
from mcp_server_roam.server import (
    call_tool,
    get_roam_client,
    list_tools,
    roam_context,
    roam_create_block,
    roam_debug_daily_notes,
    roam_get_page_markdown,
    roam_hello_world,
    serve,
    server,
)

ROAM_CLIENT_PATH = "mcp_server_roam.server.get_roam_client"


# Fixtures for mock data
@pytest.fixture
def mock_page_data_simple() -> dict[str, Any]:
    """Simple page with two top-level blocks."""
    return {
        ":node/title": "Test Page",
        ":block/uid": "test-page-uid",
        ":block/children": [
            {
                ":block/string": "First block content",
                ":block/uid": "block-1",
            },
            {
                ":block/string": "Second block content",
                ":block/uid": "block-2",
            },
        ],
    }


@pytest.fixture
def mock_page_data_nested() -> dict[str, Any]:
    """Page with nested blocks (3 levels deep)."""
    return {
        ":node/title": "Nested Page",
        ":block/uid": "nested-page-uid",
        ":block/children": [
            {
                ":block/string": "Top level block",
                ":block/uid": "top-1",
                ":block/children": [
                    {
                        ":block/string": "Second level block",
                        ":block/uid": "second-1",
                        ":block/children": [
                            {
                                ":block/string": "Third level block",
                                ":block/uid": "third-1",
                            }
                        ],
                    },
                    {
                        ":block/string": "Another second level",
                        ":block/uid": "second-2",
                    },
                ],
            },
            {
                ":block/string": "Another top level",
                ":block/uid": "top-2",
            },
        ],
    }


@pytest.fixture
def mock_page_data_empty() -> dict[str, Any]:
    """Page with no children blocks."""
    return {
        ":node/title": "Empty Page",
        ":block/uid": "empty-page-uid",
        ":block/children": [],
    }


# Tests for roam_hello_world
class TestRoamHelloWorld:
    """Tests for the simple hello world function."""

    def test_hello_world_default(self) -> None:
        """Test hello world with default parameter."""
        result = roam_hello_world()
        assert "Hello, World!" in result
        assert "Roam Research MCP server" in result

    def test_hello_world_custom_name(self) -> None:
        """Test hello world with custom name parameter."""
        result = roam_hello_world("Claude")
        assert "Hello, Claude!" in result
        assert "Roam Research MCP server" in result

    def test_hello_world_empty_name(self) -> None:
        """Test hello world with empty string name."""
        result = roam_hello_world("")
        assert "Hello, !" in result


# Tests for roam_get_page_markdown
class TestRoamGetPageMarkdown:
    """Tests for fetching page content as markdown."""

    def test_get_page_markdown_simple(
        self, mocker: MockerFixture, mock_page_data_simple: dict[str, Any]
    ) -> None:
        """Test getting page markdown with simple structure."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.return_value = mock_page_data_simple
        mock_roam_instance.process_blocks.return_value = (
            "- First block content\n- Second block content\n"
        )

        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_get_page_markdown("Test Page")

        mock_roam_instance.get_page.assert_called_once_with("Test Page")
        assert "# Test Page\n\n" in result
        assert "- First block content\n" in result
        assert "- Second block content\n" in result

    def test_get_page_markdown_nested(
        self, mocker: MockerFixture, mock_page_data_nested: dict[str, Any]
    ) -> None:
        """Test getting page markdown with nested structure."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.return_value = mock_page_data_nested
        mock_roam_instance.process_blocks.return_value = (
            "- Top level block\n"
            "  - Second level block\n"
            "    - Third level block\n"
            "  - Another second level\n"
            "- Another top level\n"
        )

        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_get_page_markdown("Nested Page")

        assert "# Nested Page\n\n" in result
        assert "- Top level block\n" in result
        assert "  - Second level block\n" in result
        assert "    - Third level block\n" in result
        assert "  - Another second level\n" in result
        assert "- Another top level\n" in result

    def test_get_page_markdown_empty(
        self, mocker: MockerFixture, mock_page_data_empty: dict[str, Any]
    ) -> None:
        """Test getting page markdown for page with no blocks."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.return_value = mock_page_data_empty
        mock_roam_instance.process_blocks.return_value = ""

        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_get_page_markdown("Empty Page")

        assert result == "# Empty Page\n\n"

    def test_get_page_markdown_no_children_key(self, mocker: MockerFixture) -> None:
        """Test getting page markdown when :block/children key is missing."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.return_value = {
            ":node/title": "No Children Key",
            ":block/uid": "no-children-uid",
        }

        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_get_page_markdown("No Children Key")

        assert result == "# No Children Key\n\n"
        mock_roam_instance.process_blocks.assert_not_called()


# Tests for error handling
class TestRoamGetPageMarkdownErrors:
    """Tests for error handling in roam_get_page_markdown."""

    def test_get_page_markdown_page_not_found(self, mocker: MockerFixture) -> None:
        """Test error handling when page is not found."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.side_effect = PageNotFoundError(
            "Page with title 'Nonexistent Page' not found"
        )

        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_get_page_markdown("Nonexistent Page")

        assert "Error:" in result
        assert "not found" in result
        mock_roam_instance.get_page.assert_called_once_with("Nonexistent Page")

    def test_get_page_markdown_api_error(self, mocker: MockerFixture) -> None:
        """Test error handling when API raises a general exception."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.side_effect = RoamAPIError("API connection failed")

        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_get_page_markdown("Test Page")

        assert "Error fetching page:" in result
        assert "API connection failed" in result

    def test_get_page_markdown_authentication_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test error handling for authentication errors."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.side_effect = AuthenticationError(
            "Authentication error (HTTP 401): Invalid token"
        )

        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_get_page_markdown("Test Page")

        assert "Error fetching page:" in result
        assert "Authentication error" in result

    def test_get_page_markdown_roam_client_init_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test error handling when RoamAPI initialization fails."""
        mocker.patch(
            ROAM_CLIENT_PATH,
            side_effect=RoamAPIError(
                "Failed to initialize RoamAPI client: Roam API token not provided"
            ),
        )

        result = roam_get_page_markdown("Test Page")

        assert "Error fetching page:" in result
        assert "Failed to initialize RoamAPI client" in result


# Integration-style tests (still mocked, but testing the full flow)
class TestRoamGetPageMarkdownIntegration:
    """Integration-style tests for the full markdown conversion flow."""

    def test_real_world_page_structure(self, mocker: MockerFixture) -> None:
        """Test with a realistic page structure including references."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.return_value = {
            ":node/title": "Project Planning",
            ":block/uid": "project-uid",
            ":block/children": [
                {
                    ":block/string": "Project goals",
                    ":block/uid": "goals-uid",
                    ":block/children": [
                        {
                            ":block/string": "TODO Implement feature [[Feature A]]",
                            ":block/uid": "todo-1",
                        },
                        {
                            ":block/string": "DONE Research options #research",
                            ":block/uid": "done-1",
                        },
                    ],
                },
                {
                    ":block/string": "Meeting notes from [[June 1st, 2025]]",
                    ":block/uid": "notes-uid",
                },
            ],
        }
        mock_roam_instance.process_blocks.return_value = (
            "- Project goals\n"
            "  - TODO Implement feature [[Feature A]]\n"
            "  - DONE Research options #research\n"
            "- Meeting notes from [[June 1st, 2025]]\n"
        )

        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_get_page_markdown("Project Planning")

        assert "# Project Planning\n\n" in result
        assert "- Project goals\n" in result
        assert "  - TODO Implement feature [[Feature A]]\n" in result
        assert "  - DONE Research options #research\n" in result
        assert "- Meeting notes from [[June 1st, 2025]]\n" in result

    def test_deeply_nested_structure(self, mocker: MockerFixture) -> None:
        """Test with a deeply nested structure (5+ levels)."""
        mock_roam_instance = mocker.MagicMock()

        # Create a deeply nested structure
        level_5 = {":block/string": "Level 5", ":block/uid": "l5"}
        level_4 = {
            ":block/string": "Level 4",
            ":block/uid": "l4",
            ":block/children": [level_5],
        }
        level_3 = {
            ":block/string": "Level 3",
            ":block/uid": "l3",
            ":block/children": [level_4],
        }
        level_2 = {
            ":block/string": "Level 2",
            ":block/uid": "l2",
            ":block/children": [level_3],
        }
        level_1 = {
            ":block/string": "Level 1",
            ":block/uid": "l1",
            ":block/children": [level_2],
        }

        mock_roam_instance.get_page.return_value = {
            ":node/title": "Deep Nesting",
            ":block/uid": "deep-uid",
            ":block/children": [level_1],
        }
        mock_roam_instance.process_blocks.return_value = (
            "- Level 1\n"
            "  - Level 2\n"
            "    - Level 3\n"
            "      - Level 4\n"
            "        - Level 5\n"
        )

        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_get_page_markdown("Deep Nesting")

        assert "- Level 1\n" in result
        assert "  - Level 2\n" in result
        assert "    - Level 3\n" in result
        assert "      - Level 4\n" in result
        assert "        - Level 5\n" in result


# Tests for get_roam_client singleton
class TestGetRoamClient:
    """Tests for the get_roam_client singleton."""

    def test_get_roam_client_creates_instance(self, mocker: MockerFixture) -> None:
        """Test that get_roam_client creates a RoamAPI instance."""
        import mcp_server_roam.server as server_module

        # Reset the singleton
        server_module._roam_client = None

        mock_roam_class = mocker.patch("mcp_server_roam.server.RoamAPI")
        mock_instance = mocker.MagicMock()
        mock_roam_class.return_value = mock_instance

        result = get_roam_client()

        assert result == mock_instance
        mock_roam_class.assert_called_once()

    def test_get_roam_client_returns_singleton(self, mocker: MockerFixture) -> None:
        """Test that get_roam_client returns the same instance."""
        import mcp_server_roam.server as server_module

        # Reset the singleton
        server_module._roam_client = None

        mock_roam_class = mocker.patch("mcp_server_roam.server.RoamAPI")
        mock_instance = mocker.MagicMock()
        mock_roam_class.return_value = mock_instance

        result1 = get_roam_client()
        result2 = get_roam_client()

        assert result1 is result2
        # Should only be called once since we use singleton
        mock_roam_class.assert_called_once()


# Tests for roam_create_block
class TestRoamCreateBlock:
    """Tests for roam_create_block function."""

    def test_create_block_page_not_found(self, mocker: MockerFixture) -> None:
        """Test error when page title is provided but page not found."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.run_query.return_value = []  # No results
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_create_block("Test content", title="NonexistentPage")

        assert "Error:" in result
        assert "NonexistentPage" in result
        assert "not found" in result

    def test_create_block_api_error(self, mocker: MockerFixture) -> None:
        """Test error handling when API raises an error."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.create_block.side_effect = RoamAPIError("API Error")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_create_block("Test content", page_uid="page-uid")

        assert "Error creating block:" in result
        assert "API Error" in result

    def test_create_block_invalid_query_error(self, mocker: MockerFixture) -> None:
        """Test error handling when InvalidQueryError is raised."""
        mock_roam_instance = mocker.MagicMock()
        # Simulate InvalidQueryError being raised during title lookup
        mock_roam_instance.run_query.side_effect = InvalidQueryError(
            "Input contains suspicious pattern"
        )
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_create_block("Test content", title="[:find ?e :where ...")

        assert "Error: Invalid input" in result
        assert "suspicious pattern" in result


# Tests for roam_context
class TestRoamContext:
    """Tests for roam_context function."""

    def test_context_invalid_days_zero(self) -> None:
        """Test error for days parameter < 1."""
        result = roam_context(days=0)
        assert "Error:" in result
        assert "days" in result.lower()

    def test_context_invalid_days_negative(self) -> None:
        """Test error for negative days parameter."""
        result = roam_context(days=-1)
        assert "Error:" in result
        assert "days" in result.lower()

    def test_context_invalid_days_too_large(self) -> None:
        """Test error for days parameter > 30."""
        result = roam_context(days=31)
        assert "Error:" in result
        assert "days" in result.lower()

    def test_context_invalid_max_references_zero(self) -> None:
        """Test error for max_references parameter < 1."""
        result = roam_context(days=10, max_references=0)
        assert "Error:" in result
        assert "max_references" in result.lower()

    def test_context_invalid_max_references_negative(self) -> None:
        """Test error for negative max_references parameter."""
        result = roam_context(days=10, max_references=-1)
        assert "Error:" in result
        assert "max_references" in result.lower()

    def test_context_invalid_max_references_too_large(self) -> None:
        """Test error for max_references parameter > 100."""
        result = roam_context(days=10, max_references=101)
        assert "Error:" in result
        assert "max_references" in result.lower()

    def test_context_success(self, mocker: MockerFixture) -> None:
        """Test successful context retrieval."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_daily_notes_context.return_value = "# Daily Notes"
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_context(days=5, max_references=10)

        assert result == "# Daily Notes"
        mock_roam_instance.get_daily_notes_context.assert_called_once_with(5, 10)

    def test_context_api_error(self, mocker: MockerFixture) -> None:
        """Test error handling when API raises an error."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_daily_notes_context.side_effect = RoamAPIError(
            "API Error"
        )
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_context(days=5, max_references=10)

        assert "Error fetching context:" in result
        assert "API Error" in result


# Tests for roam_debug_daily_notes
class TestRoamDebugDailyNotes:
    """Tests for roam_debug_daily_notes function."""

    def test_debug_daily_notes_success(self, mocker: MockerFixture) -> None:
        """Test successful debug output."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.find_daily_note_format.return_value = "%B %d, %Y"
        mock_roam_instance.get_page.return_value = {
            ":block/children": [{":block/string": "Test"}]
        }
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_debug_daily_notes()

        assert "Daily Notes Debug" in result
        assert "Detected format" in result
        assert "%B %d, %Y" in result

    def test_debug_daily_notes_page_not_found(self, mocker: MockerFixture) -> None:
        """Test when daily note page not found."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.find_daily_note_format.return_value = "%B %d, %Y"
        mock_roam_instance.get_page.side_effect = PageNotFoundError("Not found")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_debug_daily_notes()

        assert "Daily Notes Debug" in result
        assert "Not found" in result

    def test_debug_daily_notes_api_error_in_get_page(
        self, mocker: MockerFixture
    ) -> None:
        """Test when get_page raises API error."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.find_daily_note_format.return_value = "%B %d, %Y"
        mock_roam_instance.get_page.side_effect = RoamAPIError("API Error")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_debug_daily_notes()

        assert "Daily Notes Debug" in result
        assert "API Error" in result

    def test_debug_daily_notes_api_error_in_format(self, mocker: MockerFixture) -> None:
        """Test when find_daily_note_format raises API error."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.find_daily_note_format.side_effect = RoamAPIError(
            "API Error"
        )
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_debug_daily_notes()

        assert "Error:" in result
        assert "API Error" in result

    def test_debug_daily_notes_ordinal_format(self, mocker: MockerFixture) -> None:
        """Test debug with ordinal date format."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.find_daily_note_format.return_value = "%B %dth, %Y"
        mock_roam_instance.get_page.return_value = {
            ":block/children": [{":block/string": "Test"}]
        }
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = roam_debug_daily_notes()

        assert "Daily Notes Debug" in result
        assert "%B %dth, %Y" in result


# Tests for call_tool
class TestCallTool:
    """Tests for call_tool handler."""

    @pytest.mark.asyncio
    async def test_call_tool_hello_world(self) -> None:
        """Test call_tool handles hello_world."""
        result = await call_tool("roam_hello_world", {"name": "Test"})

        assert len(result) == 1
        assert result[0].type == "text"
        assert "Hello, Test!" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_hello_world_default(self) -> None:
        """Test call_tool handles hello_world with default name."""
        result = await call_tool("roam_hello_world", {})

        assert len(result) == 1
        assert "Hello, World!" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_get_page_markdown(self, mocker: MockerFixture) -> None:
        """Test call_tool handles get_page_markdown."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.return_value = {":block/children": []}
        mock_roam_instance.process_blocks.return_value = ""
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = await call_tool("roam_get_page_markdown", {"title": "Test Page"})

        assert len(result) == 1
        assert "Test Page" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_create_block(self, mocker: MockerFixture) -> None:
        """Test call_tool handles create_block."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.create_block.return_value = {"uid": "test-uid"}
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = await call_tool(
            "roam_create_block", {"content": "Test", "page_uid": "page123"}
        )

        assert len(result) == 1
        assert "Created block" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_context(self, mocker: MockerFixture) -> None:
        """Test call_tool handles context."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_daily_notes_context.return_value = "# Daily Notes"
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = await call_tool("roam_context", {"days": 5, "max_references": 10})

        assert len(result) == 1
        assert "Daily Notes" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_debug_daily_notes(self, mocker: MockerFixture) -> None:
        """Test call_tool handles debug_daily_notes."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.find_daily_note_format.return_value = "%B %d, %Y"
        mock_roam_instance.get_page.return_value = {":block/children": []}
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = await call_tool("roam_debug_daily_notes", {})

        assert len(result) == 1
        assert "Daily Notes Debug" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_unknown_tool(self) -> None:
        """Test call_tool raises error for unknown tool."""
        with pytest.raises(ValueError) as exc_info:
            await call_tool("unknown_tool", {})
        assert "Unknown tool" in str(exc_info.value)


# Tests for list_tools
class TestListTools:
    """Tests for list_tools handler."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_tools(self) -> None:
        """Test that list_tools returns all registered tools."""
        tools = await list_tools()

        tool_names = [tool.name for tool in tools]
        assert "roam_hello_world" in tool_names
        assert "roam_get_page_markdown" in tool_names
        assert "roam_create_block" in tool_names
        assert "roam_context" in tool_names
        assert "roam_debug_daily_notes" in tool_names
        assert len(tools) == 5


# Tests for serve function
class TestServe:
    """Tests for the serve function."""

    @pytest.mark.asyncio
    async def test_serve_initialization(self, mocker: MockerFixture) -> None:
        """Test that serve initializes and runs the server."""
        # Mock the stdio_server context manager
        mock_read_stream = mocker.MagicMock()
        mock_write_stream = mocker.MagicMock()

        mock_stdio = mocker.MagicMock()
        mock_stdio.__aenter__ = mocker.AsyncMock(
            return_value=(mock_read_stream, mock_write_stream)
        )
        mock_stdio.__aexit__ = mocker.AsyncMock(return_value=None)

        mocker.patch("mcp_server_roam.server.stdio_server", return_value=mock_stdio)

        # Mock server.run to avoid actually running
        mock_run = mocker.patch.object(server, "run", new_callable=mocker.AsyncMock)

        await serve()

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == mock_read_stream
        assert call_args[0][1] == mock_write_stream

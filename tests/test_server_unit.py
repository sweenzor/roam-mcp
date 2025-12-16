"""Unit tests for the Roam MCP server with mocked dependencies.

These tests use pytest-mock to mock external dependencies (RoamAPI) and ensure
fast, isolated testing without requiring actual Roam API access.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from mcp_server_roam.roam_api import (
    AuthenticationError,
    BlockNotFoundError,
    InvalidQueryError,
    PageNotFoundError,
    RoamAPIError,
)
from mcp_server_roam.server import (
    call_tool,
    create_block,
    daily_context,
    debug_daily_notes,
    get_backlinks,
    get_block_context,
    get_page,
    get_roam_client,
    hello_world,
    list_tools,
    raw_query,
    search_by_text,
    semantic_search,
    serve,
    server,
    sync_index,
)
from mcp_server_roam.vector_store import SyncStatus

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


# Tests for hello_world
class TestRoamHelloWorld:
    """Tests for the simple hello world function."""

    def test_hello_world_default(self) -> None:
        """Test hello world with default parameter."""
        result = hello_world()
        assert "Hello, World!" in result
        assert "Roam Research MCP server" in result

    def test_hello_world_custom_name(self) -> None:
        """Test hello world with custom name parameter."""
        result = hello_world("Claude")
        assert "Hello, Claude!" in result
        assert "Roam Research MCP server" in result

    def test_hello_world_empty_name(self) -> None:
        """Test hello world with empty string name."""
        result = hello_world("")
        assert "Hello, !" in result


# Tests for get_page
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

        result = get_page("Test Page")

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

        result = get_page("Nested Page")

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

        result = get_page("Empty Page")

        assert result == "# Empty Page\n\n"

    def test_get_page_markdown_no_children_key(self, mocker: MockerFixture) -> None:
        """Test getting page markdown when :block/children key is missing."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.return_value = {
            ":node/title": "No Children Key",
            ":block/uid": "no-children-uid",
        }

        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = get_page("No Children Key")

        assert result == "# No Children Key\n\n"
        mock_roam_instance.process_blocks.assert_not_called()


# Tests for error handling
class TestRoamGetPageMarkdownErrors:
    """Tests for error handling in get_page."""

    def test_get_page_markdown_page_not_found(self, mocker: MockerFixture) -> None:
        """Test error handling when page is not found."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.side_effect = PageNotFoundError(
            "Page with title 'Nonexistent Page' not found"
        )

        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = get_page("Nonexistent Page")

        assert "Error:" in result
        assert "not found" in result
        mock_roam_instance.get_page.assert_called_once_with("Nonexistent Page")

    def test_get_page_markdown_api_error(self, mocker: MockerFixture) -> None:
        """Test error handling when API raises a general exception."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.side_effect = RoamAPIError("API connection failed")

        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = get_page("Test Page")

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

        result = get_page("Test Page")

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

        result = get_page("Test Page")

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

        result = get_page("Project Planning")

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

        result = get_page("Deep Nesting")

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


# Tests for create_block
class TestRoamCreateBlock:
    """Tests for create_block function."""

    def test_create_block_page_not_found(self, mocker: MockerFixture) -> None:
        """Test error when page title is provided but page not found."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.run_query.return_value = []  # No results
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = create_block("Test content", title="NonexistentPage")

        assert "Error:" in result
        assert "NonexistentPage" in result
        assert "not found" in result

    def test_create_block_api_error(self, mocker: MockerFixture) -> None:
        """Test error handling when API raises an error."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.create_block.side_effect = RoamAPIError("API Error")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = create_block("Test content", page_uid="page-uid")

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

        result = create_block("Test content", title="[:find ?e :where ...")

        assert "Error: Invalid input" in result
        assert "suspicious pattern" in result


# Tests for daily_context
class TestRoamContext:
    """Tests for daily_context function."""

    def test_context_invalid_days_zero(self) -> None:
        """Test error for days parameter < 1."""
        result = daily_context(days=0)
        assert "Error:" in result
        assert "days" in result.lower()

    def test_context_invalid_days_negative(self) -> None:
        """Test error for negative days parameter."""
        result = daily_context(days=-1)
        assert "Error:" in result
        assert "days" in result.lower()

    def test_context_invalid_days_too_large(self) -> None:
        """Test error for days parameter > 30."""
        result = daily_context(days=31)
        assert "Error:" in result
        assert "days" in result.lower()

    def test_context_invalid_max_references_zero(self) -> None:
        """Test error for max_references parameter < 1."""
        result = daily_context(days=10, max_references=0)
        assert "Error:" in result
        assert "max_references" in result.lower()

    def test_context_invalid_max_references_negative(self) -> None:
        """Test error for negative max_references parameter."""
        result = daily_context(days=10, max_references=-1)
        assert "Error:" in result
        assert "max_references" in result.lower()

    def test_context_invalid_max_references_too_large(self) -> None:
        """Test error for max_references parameter > 100."""
        result = daily_context(days=10, max_references=101)
        assert "Error:" in result
        assert "max_references" in result.lower()

    def test_context_success(self, mocker: MockerFixture) -> None:
        """Test successful context retrieval."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_daily_notes_context.return_value = "# Daily Notes"
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = daily_context(days=5, max_references=10)

        assert result == "# Daily Notes"
        mock_roam_instance.get_daily_notes_context.assert_called_once_with(5, 10)

    def test_context_api_error(self, mocker: MockerFixture) -> None:
        """Test error handling when API raises an error."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_daily_notes_context.side_effect = RoamAPIError(
            "API Error"
        )
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = daily_context(days=5, max_references=10)

        assert "Error fetching context:" in result
        assert "API Error" in result


# Tests for debug_daily_notes
class TestRoamDebugDailyNotes:
    """Tests for debug_daily_notes function."""

    def test_debug_daily_notes_success(self, mocker: MockerFixture) -> None:
        """Test successful debug output."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.find_daily_note_format.return_value = "%B %d, %Y"
        mock_roam_instance.get_page.return_value = {
            ":block/children": [{":block/string": "Test"}]
        }
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = debug_daily_notes()

        assert "Daily Notes Debug" in result
        assert "Detected format" in result
        assert "%B %d, %Y" in result

    def test_debug_daily_notes_page_not_found(self, mocker: MockerFixture) -> None:
        """Test when daily note page not found."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.find_daily_note_format.return_value = "%B %d, %Y"
        mock_roam_instance.get_page.side_effect = PageNotFoundError("Not found")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = debug_daily_notes()

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

        result = debug_daily_notes()

        assert "Daily Notes Debug" in result
        assert "API Error" in result

    def test_debug_daily_notes_api_error_in_format(self, mocker: MockerFixture) -> None:
        """Test when find_daily_note_format raises API error."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.find_daily_note_format.side_effect = RoamAPIError(
            "API Error"
        )
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = debug_daily_notes()

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

        result = debug_daily_notes()

        assert "Daily Notes Debug" in result
        assert "%B %dth, %Y" in result


# Tests for sync_index
class TestRoamSyncIndex:
    """Tests for sync_index function."""

    def test_sync_index_full_sync(self, mocker: MockerFixture) -> None:
        """Test full sync when explicitly requested."""
        import numpy as np

        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_all_blocks_for_sync.return_value = [
            {"uid": "b1", "content": "Test", "page_title": "P1", "edit_time": 1000}
        ]
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mock_embedding = mocker.MagicMock()
        mock_embedding.format_block_for_embedding.return_value = "formatted"
        mock_embedding.embed_texts.return_value = np.array([[0.1] * 384])
        mocker.patch(
            "mcp_server_roam.server.get_embedding_service", return_value=mock_embedding
        )

        result = sync_index(full=True)

        assert "Full sync completed" in result
        mock_store.drop_all_data.assert_called_once()
        mock_roam.get_all_blocks_for_sync.assert_called_once()

    def test_sync_index_incremental(self, mocker: MockerFixture) -> None:
        """Test incremental sync when previous sync exists."""
        import numpy as np

        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_blocks_modified_since.return_value = [
            {"uid": "b1", "content": "Test", "page_title": "P1", "edit_time": 2000}
        ]
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mock_store.get_last_sync_timestamp.return_value = 1000
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mock_embedding = mocker.MagicMock()
        mock_embedding.format_block_for_embedding.return_value = "formatted"
        mock_embedding.embed_texts.return_value = np.array([[0.1] * 384])
        mocker.patch(
            "mcp_server_roam.server.get_embedding_service", return_value=mock_embedding
        )

        result = sync_index(full=False)

        assert "Incremental sync completed" in result
        mock_roam.get_blocks_modified_since.assert_called_once_with(1000)

    def test_sync_index_no_blocks(self, mocker: MockerFixture) -> None:
        """Test sync when no blocks to process."""
        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_blocks_modified_since.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mock_store.get_last_sync_timestamp.return_value = 1000
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mocker.patch("mcp_server_roam.server.get_embedding_service")

        result = sync_index(full=False)

        assert "No blocks to sync" in result

    def test_sync_index_not_initialized(self, mocker: MockerFixture) -> None:
        """Test full sync when store is not initialized."""
        import numpy as np

        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_all_blocks_for_sync.return_value = [
            {"uid": "b1", "content": "Test", "page_title": "P1", "edit_time": 1000}
        ]
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.NOT_INITIALIZED
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mock_embedding = mocker.MagicMock()
        mock_embedding.format_block_for_embedding.return_value = "formatted"
        mock_embedding.embed_texts.return_value = np.array([[0.1] * 384])
        mocker.patch(
            "mcp_server_roam.server.get_embedding_service", return_value=mock_embedding
        )

        result = sync_index(full=False)

        assert "Full sync completed" in result
        mock_store.drop_all_data.assert_called_once()

    def test_sync_index_api_error(self, mocker: MockerFixture) -> None:
        """Test error handling for API errors."""
        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_all_blocks_for_sync.side_effect = RoamAPIError("API Error")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.NOT_INITIALIZED
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mocker.patch("mcp_server_roam.server.get_embedding_service")

        result = sync_index(full=True)

        assert "Error during sync" in result
        assert "API Error" in result

    def test_sync_index_unexpected_error(self, mocker: MockerFixture) -> None:
        """Test error handling for unexpected errors."""
        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_all_blocks_for_sync.side_effect = ValueError("Unexpected")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.NOT_INITIALIZED
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mocker.patch("mcp_server_roam.server.get_embedding_service")

        result = sync_index(full=True)

        assert "Unexpected error" in result

    def test_sync_index_no_timestamp_does_full(self, mocker: MockerFixture) -> None:
        """Test full sync when no previous timestamp exists."""
        import numpy as np

        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_all_blocks_for_sync.return_value = [
            {"uid": "b1", "content": "Test", "page_title": "P1", "edit_time": 1000}
        ]
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mock_store.get_last_sync_timestamp.return_value = None
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mock_embedding = mocker.MagicMock()
        mock_embedding.format_block_for_embedding.return_value = "formatted"
        mock_embedding.embed_texts.return_value = np.array([[0.1] * 384])
        mocker.patch(
            "mcp_server_roam.server.get_embedding_service", return_value=mock_embedding
        )

        sync_index(full=False)

        # Should do full sync since no timestamp
        mock_roam.get_all_blocks_for_sync.assert_called_once()

    def test_sync_index_multiple_batches_progress_logging(
        self, mocker: MockerFixture
    ) -> None:
        """Test progress logging with multiple batches."""
        import numpy as np

        # Create 650 blocks to trigger 11 batches (10th batch logs)
        blocks = [
            {
                "uid": f"b{i}",
                "content": f"Test {i}",
                "page_title": "P1",
                "edit_time": 1000,
            }
            for i in range(650)
        ]

        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_all_blocks_for_sync.return_value = blocks
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.NOT_INITIALIZED
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mock_embedding = mocker.MagicMock()
        mock_embedding.format_block_for_embedding.return_value = "formatted"
        # Return embeddings for each batch
        mock_embedding.embed_texts.return_value = np.array([[0.1] * 384] * 64)
        mocker.patch(
            "mcp_server_roam.server.get_embedding_service", return_value=mock_embedding
        )

        result = sync_index(full=True)

        assert "Full sync completed" in result
        assert "650 blocks" in result


# Tests for semantic_search
class TestRoamSemanticSearch:
    """Tests for semantic_search function."""

    def test_search_not_initialized(self, mocker: MockerFixture) -> None:
        """Test search returns message when index not initialized."""
        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.NOT_INITIALIZED
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mocker.patch("mcp_server_roam.server.get_embedding_service")

        result = semantic_search("test query")

        assert "not initialized" in result.lower()
        assert "sync_index" in result

    def test_search_with_results(self, mocker: MockerFixture) -> None:
        """Test search returns formatted results."""
        import numpy as np

        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_blocks_modified_since.return_value = []
        mock_roam.get_block_parent_chain.return_value = ["Parent 1"]
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mock_store.get_last_sync_timestamp.return_value = 1000
        mock_store.search.return_value = [
            {
                "uid": "block-1",
                "content": "Test content",
                "page_title": "Test Page",
                "similarity": 0.8,
                "parent_chain": None,
            }
        ]
        # Mock the edit_time lookup
        mock_cursor = mocker.MagicMock()
        mock_cursor.fetchone.return_value = {"edit_time": 1000}
        mock_store.conn.execute.return_value = mock_cursor
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mock_embedding = mocker.MagicMock()
        mock_embedding.embed_single.return_value = np.array([0.1] * 384)
        mocker.patch(
            "mcp_server_roam.server.get_embedding_service", return_value=mock_embedding
        )

        result = semantic_search("test query")

        assert "Search Results" in result
        assert "Test Page" in result
        assert "Test content" in result
        assert "block-1" in result

    def test_search_no_results(self, mocker: MockerFixture) -> None:
        """Test search returns message when no results found."""
        import numpy as np

        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_blocks_modified_since.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mock_store.get_last_sync_timestamp.return_value = 1000
        mock_store.search.return_value = []
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mock_embedding = mocker.MagicMock()
        mock_embedding.embed_single.return_value = np.array([0.1] * 384)
        mocker.patch(
            "mcp_server_roam.server.get_embedding_service", return_value=mock_embedding
        )

        result = semantic_search("obscure query")

        assert "No results found" in result

    def test_search_with_incremental_sync(self, mocker: MockerFixture) -> None:
        """Test search performs incremental sync when blocks modified."""
        import numpy as np

        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_blocks_modified_since.return_value = [
            {"uid": "new-block", "content": "New", "page_title": "P", "edit_time": 2000}
        ]
        mock_roam.get_block_parent_chain.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mock_store.get_last_sync_timestamp.return_value = 1000
        mock_store.search.return_value = [
            {
                "uid": "block-1",
                "content": "Content",
                "page_title": "Page",
                "similarity": 0.7,
                "parent_chain": None,
            }
        ]
        mock_cursor = mocker.MagicMock()
        mock_cursor.fetchone.return_value = {"edit_time": 1000}
        mock_store.conn.execute.return_value = mock_cursor
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mock_embedding = mocker.MagicMock()
        mock_embedding.embed_single.return_value = np.array([0.1] * 384)
        mock_embedding.embed_texts.return_value = np.array([[0.1] * 384])
        mock_embedding.format_block_for_embedding.return_value = "formatted"
        mocker.patch(
            "mcp_server_roam.server.get_embedding_service", return_value=mock_embedding
        )

        semantic_search("test")

        # Should have synced the new block
        mock_store.upsert_blocks.assert_called_once()
        mock_store.upsert_embeddings.assert_called_once()
        mock_store.set_last_sync_timestamp.assert_called_once_with(2000)

    def test_search_without_context(self, mocker: MockerFixture) -> None:
        """Test search with include_context=False."""
        import numpy as np

        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_blocks_modified_since.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mock_store.get_last_sync_timestamp.return_value = 1000
        mock_store.search.return_value = [
            {
                "uid": "block-1",
                "content": "Content",
                "page_title": "Page",
                "similarity": 0.7,
                "parent_chain": None,
            }
        ]
        mock_cursor = mocker.MagicMock()
        mock_cursor.fetchone.return_value = {"edit_time": 1000}
        mock_store.conn.execute.return_value = mock_cursor
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mock_embedding = mocker.MagicMock()
        mock_embedding.embed_single.return_value = np.array([0.1] * 384)
        mocker.patch(
            "mcp_server_roam.server.get_embedding_service", return_value=mock_embedding
        )

        semantic_search("test", include_context=False)

        # Should not fetch parent chain
        mock_roam.get_block_parent_chain.assert_not_called()

    def test_search_api_error(self, mocker: MockerFixture) -> None:
        """Test search handles API errors gracefully."""
        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mock_store.get_last_sync_timestamp.side_effect = RoamAPIError("API Error")
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mocker.patch("mcp_server_roam.server.get_embedding_service")

        result = semantic_search("test")

        assert "Error during search" in result

    def test_search_unexpected_error(self, mocker: MockerFixture) -> None:
        """Test search handles unexpected errors gracefully."""
        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mock_store.get_last_sync_timestamp.side_effect = ValueError("Unexpected")
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mocker.patch("mcp_server_roam.server.get_embedding_service")

        result = semantic_search("test")

        assert "Unexpected error" in result

    def test_search_truncates_long_content(self, mocker: MockerFixture) -> None:
        """Test search truncates content over 500 chars."""
        import numpy as np

        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_blocks_modified_since.return_value = []
        mock_roam.get_block_parent_chain.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        long_content = "A" * 600
        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mock_store.get_last_sync_timestamp.return_value = 1000
        mock_store.search.return_value = [
            {
                "uid": "block-1",
                "content": long_content,
                "page_title": "Page",
                "similarity": 0.7,
                "parent_chain": None,
            }
        ]
        mock_cursor = mocker.MagicMock()
        mock_cursor.fetchone.return_value = {"edit_time": 1000}
        mock_store.conn.execute.return_value = mock_cursor
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mock_embedding = mocker.MagicMock()
        mock_embedding.embed_single.return_value = np.array([0.1] * 384)
        mocker.patch(
            "mcp_server_roam.server.get_embedding_service", return_value=mock_embedding
        )

        result = semantic_search("test")

        # Content should be truncated
        assert "..." in result
        assert len(result) < len(long_content) + 200  # Reasonable output size

    def test_search_no_timestamp_skips_incremental(self, mocker: MockerFixture) -> None:
        """Test search skips incremental sync when no timestamp."""
        import numpy as np

        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_block_parent_chain.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mock_store.get_last_sync_timestamp.return_value = None  # No timestamp
        mock_store.search.return_value = [
            {
                "uid": "block-1",
                "content": "Content",
                "page_title": "Page",
                "similarity": 0.7,
                "parent_chain": None,
            }
        ]
        mock_cursor = mocker.MagicMock()
        mock_cursor.fetchone.return_value = {"edit_time": 1000}
        mock_store.conn.execute.return_value = mock_cursor
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mock_embedding = mocker.MagicMock()
        mock_embedding.embed_single.return_value = np.array([0.1] * 384)
        mocker.patch(
            "mcp_server_roam.server.get_embedding_service", return_value=mock_embedding
        )

        result = semantic_search("test")

        # Should not try to get modified blocks
        mock_roam.get_blocks_modified_since.assert_not_called()
        assert "Search Results" in result

    def test_search_with_recency_boost(self, mocker: MockerFixture) -> None:
        """Test search applies recency boost to recent blocks."""
        import time as time_module

        import numpy as np

        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_blocks_modified_since.return_value = []
        mock_roam.get_block_parent_chain.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        # Use a very recent timestamp (now)
        recent_time = int(time_module.time() * 1000)
        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mock_store.get_last_sync_timestamp.return_value = 1000
        mock_store.search.return_value = [
            {
                "uid": "block-1",
                "content": "Content",
                "page_title": "Page",
                "similarity": 0.7,
                "parent_chain": None,
            }
        ]
        mock_cursor = mocker.MagicMock()
        mock_cursor.fetchone.return_value = {"edit_time": recent_time}
        mock_store.conn.execute.return_value = mock_cursor
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mock_embedding = mocker.MagicMock()
        mock_embedding.embed_single.return_value = np.array([0.1] * 384)
        mocker.patch(
            "mcp_server_roam.server.get_embedding_service", return_value=mock_embedding
        )

        result = semantic_search("test")

        assert "Search Results" in result

    def test_search_with_existing_parent_chain(self, mocker: MockerFixture) -> None:
        """Test search uses existing parent_chain without fetching."""
        import numpy as np

        mock_roam = mocker.MagicMock()
        mock_roam.graph_name = "test-graph"
        mock_roam.get_blocks_modified_since.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        mock_store = mocker.MagicMock()
        mock_store.get_sync_status.return_value = SyncStatus.COMPLETED
        mock_store.get_last_sync_timestamp.return_value = 1000
        mock_store.search.return_value = [
            {
                "uid": "block-1",
                "content": "Content",
                "page_title": "Page",
                "similarity": 0.7,
                "parent_chain": ["Already", "Exists"],  # Already has parent chain
            }
        ]
        mock_cursor = mocker.MagicMock()
        mock_cursor.fetchone.return_value = {"edit_time": 1000}
        mock_store.conn.execute.return_value = mock_cursor
        mocker.patch("mcp_server_roam.server.get_vector_store", return_value=mock_store)

        mock_embedding = mocker.MagicMock()
        mock_embedding.embed_single.return_value = np.array([0.1] * 384)
        mocker.patch(
            "mcp_server_roam.server.get_embedding_service", return_value=mock_embedding
        )

        result = semantic_search("test", include_context=True)

        # Should not fetch parent chain since it already exists
        mock_roam.get_block_parent_chain.assert_not_called()
        assert "Already > Exists" in result


# Tests for call_tool
class TestCallTool:
    """Tests for call_tool handler."""

    @pytest.mark.asyncio
    async def test_call_tool_hello_world(self) -> None:
        """Test call_tool handles hello_world."""
        result = await call_tool("hello_world", {"name": "Test"})

        assert len(result) == 1
        assert result[0].type == "text"
        assert "Hello, Test!" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_hello_world_default(self) -> None:
        """Test call_tool handles hello_world with default name."""
        result = await call_tool("hello_world", {})

        assert len(result) == 1
        assert "Hello, World!" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_get_page_markdown(self, mocker: MockerFixture) -> None:
        """Test call_tool handles get_page_markdown."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.return_value = {":block/children": []}
        mock_roam_instance.process_blocks.return_value = ""
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = await call_tool("get_page", {"title": "Test Page"})

        assert len(result) == 1
        assert "Test Page" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_create_block(self, mocker: MockerFixture) -> None:
        """Test call_tool handles create_block."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.create_block.return_value = {"uid": "test-uid"}
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = await call_tool(
            "create_block", {"content": "Test", "page_uid": "page123"}
        )

        assert len(result) == 1
        assert "Created block" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_context(self, mocker: MockerFixture) -> None:
        """Test call_tool handles context."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_daily_notes_context.return_value = "# Daily Notes"
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = await call_tool("daily_context", {"days": 5, "max_references": 10})

        assert len(result) == 1
        assert "Daily Notes" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_debug_daily_notes(self, mocker: MockerFixture) -> None:
        """Test call_tool handles debug_daily_notes."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.find_daily_note_format.return_value = "%B %d, %Y"
        mock_roam_instance.get_page.return_value = {":block/children": []}
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam_instance)

        result = await call_tool("debug_daily_notes", {})

        assert len(result) == 1
        assert "Daily Notes Debug" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_sync_index(self, mocker: MockerFixture) -> None:
        """Test call_tool handles sync_index."""
        mock_sync = mocker.patch(
            "mcp_server_roam.server.sync_index",
            return_value="Sync completed",
        )

        result = await call_tool("sync_index", {"full": True})

        assert len(result) == 1
        assert "Sync completed" in result[0].text
        mock_sync.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_call_tool_sync_index_default(self, mocker: MockerFixture) -> None:
        """Test call_tool handles sync_index with default args."""
        mock_sync = mocker.patch(
            "mcp_server_roam.server.sync_index",
            return_value="Sync completed",
        )

        result = await call_tool("sync_index", {})

        assert len(result) == 1
        mock_sync.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_call_tool_semantic_search(self, mocker: MockerFixture) -> None:
        """Test call_tool handles semantic_search."""
        mock_search = mocker.patch(
            "mcp_server_roam.server.semantic_search",
            return_value="Search results",
        )

        result = await call_tool(
            "semantic_search",
            {"query": "test", "limit": 5, "include_context": False},
        )

        assert len(result) == 1
        assert "Search results" in result[0].text
        mock_search.assert_called_once_with("test", 5, False)

    @pytest.mark.asyncio
    async def test_call_tool_semantic_search_defaults(
        self, mocker: MockerFixture
    ) -> None:
        """Test call_tool handles semantic_search with default args."""
        mock_search = mocker.patch(
            "mcp_server_roam.server.semantic_search",
            return_value="Search results",
        )

        result = await call_tool("semantic_search", {"query": "test"})

        assert len(result) == 1
        mock_search.assert_called_once_with("test", 10, True)

    @pytest.mark.asyncio
    async def test_call_tool_get_block_context(self, mocker: MockerFixture) -> None:
        """Test call_tool handles get_block_context."""
        mock_get_block = mocker.patch(
            "mcp_server_roam.server.get_block_context",
            return_value="Block context",
        )

        result = await call_tool("get_block_context", {"uid": "test-uid"})

        assert len(result) == 1
        assert "Block context" in result[0].text
        mock_get_block.assert_called_once_with("test-uid")

    @pytest.mark.asyncio
    async def test_call_tool_search_by_text(self, mocker: MockerFixture) -> None:
        """Test call_tool handles search_by_text."""
        mock_search = mocker.patch(
            "mcp_server_roam.server.search_by_text",
            return_value="Search results",
        )

        result = await call_tool(
            "search_by_text",
            {"text": "query", "page_title": "Page", "limit": 10},
        )

        assert len(result) == 1
        assert "Search results" in result[0].text
        mock_search.assert_called_once_with("query", "Page", 10)

    @pytest.mark.asyncio
    async def test_call_tool_search_by_text_defaults(
        self, mocker: MockerFixture
    ) -> None:
        """Test call_tool handles search_by_text with defaults."""
        mock_search = mocker.patch(
            "mcp_server_roam.server.search_by_text",
            return_value="Search results",
        )

        await call_tool("search_by_text", {"text": "query"})

        mock_search.assert_called_once_with("query", None, 20)

    @pytest.mark.asyncio
    async def test_call_tool_raw_query(self, mocker: MockerFixture) -> None:
        """Test call_tool handles raw_query."""
        mock_query = mocker.patch(
            "mcp_server_roam.server.raw_query",
            return_value='[["result"]]',
        )

        result = await call_tool(
            "raw_query",
            {"query": "[:find ?e]", "args": ["arg1"]},
        )

        assert len(result) == 1
        mock_query.assert_called_once_with("[:find ?e]", ["arg1"])

    @pytest.mark.asyncio
    async def test_call_tool_raw_query_defaults(self, mocker: MockerFixture) -> None:
        """Test call_tool handles raw_query with defaults."""
        mock_query = mocker.patch(
            "mcp_server_roam.server.raw_query",
            return_value="[]",
        )

        await call_tool("raw_query", {"query": "[:find ?e]"})

        mock_query.assert_called_once_with("[:find ?e]", None)

    @pytest.mark.asyncio
    async def test_call_tool_get_backlinks(self, mocker: MockerFixture) -> None:
        """Test call_tool handles get_backlinks."""
        mock_backlinks = mocker.patch(
            "mcp_server_roam.server.get_backlinks",
            return_value="Backlinks",
        )

        result = await call_tool(
            "get_backlinks",
            {"page_title": "Test Page", "limit": 10},
        )

        assert len(result) == 1
        assert "Backlinks" in result[0].text
        mock_backlinks.assert_called_once_with("Test Page", 10)

    @pytest.mark.asyncio
    async def test_call_tool_get_backlinks_defaults(
        self, mocker: MockerFixture
    ) -> None:
        """Test call_tool handles get_backlinks with defaults."""
        mock_backlinks = mocker.patch(
            "mcp_server_roam.server.get_backlinks",
            return_value="Backlinks",
        )

        await call_tool("get_backlinks", {"page_title": "Page"})

        mock_backlinks.assert_called_once_with("Page", 20)

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
        assert "hello_world" in tool_names
        assert "get_page" in tool_names
        assert "create_block" in tool_names
        assert "daily_context" in tool_names
        assert "debug_daily_notes" in tool_names
        assert "sync_index" in tool_names
        assert "semantic_search" in tool_names
        assert "get_block_context" in tool_names
        assert "search_by_text" in tool_names
        assert "raw_query" in tool_names
        assert "get_backlinks" in tool_names
        assert len(tools) == 11


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


# Tests for get_block_context
class TestGetBlockContext:
    """Tests for get_block_context tool."""

    def test_get_block_context_success(self, mocker: MockerFixture) -> None:
        """Test successful block context retrieval."""
        mock_roam = mocker.MagicMock()
        mock_roam.get_block.return_value = {
            ":block/string": "Test block content",
            ":block/children": [
                {":block/string": "Child 1"},
                {":block/string": "Child 2"},
            ],
        }
        mock_roam.get_block_parent_chain.return_value = ["Parent 1", "Parent 2"]
        mock_roam.process_blocks.return_value = "- Child 1\n- Child 2\n"
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = get_block_context("test-uid")

        assert "Block Context" in result
        assert "Test block content" in result
        assert "Parent 1 > Parent 2" in result
        assert "Children" in result
        mock_roam.get_block.assert_called_once_with("test-uid")
        mock_roam.get_block_parent_chain.assert_called_once_with("test-uid")

    def test_get_block_context_no_parent_chain(self, mocker: MockerFixture) -> None:
        """Test block context without parent chain."""
        mock_roam = mocker.MagicMock()
        mock_roam.get_block.return_value = {
            ":block/string": "Root block",
        }
        mock_roam.get_block_parent_chain.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = get_block_context("root-uid")

        assert "Root block" in result
        assert "Path:" not in result

    def test_get_block_context_not_found(self, mocker: MockerFixture) -> None:
        """Test block not found error."""
        mock_roam = mocker.MagicMock()
        mock_roam.get_block.side_effect = BlockNotFoundError("Block not found")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = get_block_context("nonexistent")

        assert "Error" in result
        assert "not found" in result.lower()

    def test_get_block_context_api_error(self, mocker: MockerFixture) -> None:
        """Test API error handling."""
        mock_roam = mocker.MagicMock()
        mock_roam.get_block.side_effect = RoamAPIError("API Error")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = get_block_context("test-uid")

        assert "Error" in result
        assert "fetching block" in result.lower()

    def test_get_block_context_with_page_title(self, mocker: MockerFixture) -> None:
        """Test block context when block has a page title (is a page)."""
        mock_roam = mocker.MagicMock()
        mock_roam.get_block.return_value = {
            ":block/string": "Page content",
            ":node/title": "My Page Title",
        }
        mock_roam.get_block_parent_chain.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = get_block_context("page-uid")

        assert "My Page Title" in result
        assert "Page:" in result


# Tests for search_by_text
class TestSearchByText:
    """Tests for search_by_text tool."""

    def test_search_by_text_success(self, mocker: MockerFixture) -> None:
        """Test successful text search."""
        mock_roam = mocker.MagicMock()
        mock_roam.search_blocks_by_text.return_value = [
            {"uid": "uid1", "content": "First match", "page_title": "Page 1"},
            {"uid": "uid2", "content": "Second match", "page_title": "Page 2"},
        ]
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = search_by_text("test query")

        assert "Text Search Results" in result
        assert "test query" in result
        assert "First match" in result
        assert "Second match" in result
        assert "Page 1" in result
        mock_roam.search_blocks_by_text.assert_called_once_with("test query", None, 20)

    def test_search_by_text_with_page_filter(self, mocker: MockerFixture) -> None:
        """Test text search with page filter."""
        mock_roam = mocker.MagicMock()
        mock_roam.search_blocks_by_text.return_value = [
            {"uid": "uid1", "content": "Filtered match", "page_title": "Specific Page"},
        ]
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = search_by_text("query", page_title="Specific Page", limit=10)

        assert "Filtered match" in result
        assert "Scope:" in result
        assert "Specific Page" in result
        mock_roam.search_blocks_by_text.assert_called_once_with(
            "query", "Specific Page", 10
        )

    def test_search_by_text_no_results(self, mocker: MockerFixture) -> None:
        """Test text search with no results."""
        mock_roam = mocker.MagicMock()
        mock_roam.search_blocks_by_text.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = search_by_text("nonexistent")

        assert "No blocks found" in result
        assert "nonexistent" in result

    def test_search_by_text_no_results_with_page(self, mocker: MockerFixture) -> None:
        """Test text search with no results in specific page."""
        mock_roam = mocker.MagicMock()
        mock_roam.search_blocks_by_text.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = search_by_text("query", page_title="Empty Page")

        assert "No blocks found" in result
        assert "in page 'Empty Page'" in result

    def test_search_by_text_invalid_query(self, mocker: MockerFixture) -> None:
        """Test invalid query error."""
        mock_roam = mocker.MagicMock()
        mock_roam.search_blocks_by_text.side_effect = InvalidQueryError("Invalid")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = search_by_text("[:find")

        assert "Error" in result
        assert "Invalid" in result

    def test_search_by_text_api_error(self, mocker: MockerFixture) -> None:
        """Test API error handling."""
        mock_roam = mocker.MagicMock()
        mock_roam.search_blocks_by_text.side_effect = RoamAPIError("Server error")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = search_by_text("query")

        assert "Error" in result
        assert "searching blocks" in result.lower()

    def test_search_by_text_truncates_long_content(self, mocker: MockerFixture) -> None:
        """Test long content is truncated."""
        mock_roam = mocker.MagicMock()
        mock_roam.search_blocks_by_text.return_value = [
            {"uid": "uid1", "content": "x" * 600, "page_title": "Page"},
        ]
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = search_by_text("query")

        assert "..." in result
        assert len(result) < 700


# Tests for raw_query
class TestRawQuery:
    """Tests for raw_query tool."""

    def test_raw_query_success(self, mocker: MockerFixture) -> None:
        """Test successful raw query."""
        mock_roam = mocker.MagicMock()
        mock_roam.run_query.return_value = [
            ["uid1", "content1"],
            ["uid2", "content2"],
        ]
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = raw_query("[:find ?e :where [?e :block/uid]]")

        assert "uid1" in result
        assert "content1" in result
        mock_roam.run_query.assert_called_once_with(
            "[:find ?e :where [?e :block/uid]]", None
        )

    def test_raw_query_with_args(self, mocker: MockerFixture) -> None:
        """Test raw query with arguments."""
        mock_roam = mocker.MagicMock()
        mock_roam.run_query.return_value = [["result"]]
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        raw_query(
            "[:find ?e :in $ ?title :where [?e :node/title ?title]]", args=["Test Page"]
        )

        mock_roam.run_query.assert_called_once_with(
            "[:find ?e :in $ ?title :where [?e :node/title ?title]]", ["Test Page"]
        )

    def test_raw_query_empty_results(self, mocker: MockerFixture) -> None:
        """Test raw query with empty results."""
        mock_roam = mocker.MagicMock()
        mock_roam.run_query.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = raw_query("[:find ?e :where [?e :nonexistent/attr]]")

        assert result == "[]"

    def test_raw_query_invalid(self, mocker: MockerFixture) -> None:
        """Test invalid query error."""
        mock_roam = mocker.MagicMock()
        mock_roam.run_query.side_effect = InvalidQueryError("Syntax error")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = raw_query("invalid query")

        assert "Error" in result
        assert "Invalid query" in result

    def test_raw_query_api_error(self, mocker: MockerFixture) -> None:
        """Test API error handling."""
        mock_roam = mocker.MagicMock()
        mock_roam.run_query.side_effect = RoamAPIError("Server error")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = raw_query("[:find ?e]")

        assert "Error" in result
        assert "executing query" in result.lower()


# Tests for get_backlinks
class TestGetBacklinks:
    """Tests for get_backlinks tool."""

    def test_get_backlinks_success(self, mocker: MockerFixture) -> None:
        """Test successful backlinks retrieval."""
        mock_roam = mocker.MagicMock()
        mock_roam.get_references_to_page.return_value = [
            {"uid": "uid1", "string": "Reference to [[Test Page]]"},
            {"uid": "uid2", "string": "Another [[Test Page]] mention"},
        ]
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = get_backlinks("Test Page")

        assert "Backlinks to: Test Page" in result
        assert "Reference to" in result
        assert "Another" in result
        mock_roam.get_references_to_page.assert_called_once_with("Test Page", 20)

    def test_get_backlinks_custom_limit(self, mocker: MockerFixture) -> None:
        """Test backlinks with custom limit."""
        mock_roam = mocker.MagicMock()
        mock_roam.get_references_to_page.return_value = [
            {"uid": "uid1", "string": "Single ref"},
        ]
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        get_backlinks("Page", limit=5)

        mock_roam.get_references_to_page.assert_called_once_with("Page", 5)

    def test_get_backlinks_no_results(self, mocker: MockerFixture) -> None:
        """Test backlinks with no results."""
        mock_roam = mocker.MagicMock()
        mock_roam.get_references_to_page.return_value = []
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = get_backlinks("Isolated Page")

        assert "No blocks found referencing" in result
        assert "Isolated Page" in result

    def test_get_backlinks_invalid_page(self, mocker: MockerFixture) -> None:
        """Test invalid page title error."""
        mock_roam = mocker.MagicMock()
        mock_roam.get_references_to_page.side_effect = InvalidQueryError("Invalid")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = get_backlinks("[:find")

        assert "Error" in result
        assert "Invalid page title" in result

    def test_get_backlinks_api_error(self, mocker: MockerFixture) -> None:
        """Test API error handling."""
        mock_roam = mocker.MagicMock()
        mock_roam.get_references_to_page.side_effect = RoamAPIError("API Error")
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = get_backlinks("Test Page")

        assert "Error" in result
        assert "fetching backlinks" in result.lower()

    def test_get_backlinks_truncates_long_content(self, mocker: MockerFixture) -> None:
        """Test long content is truncated."""
        mock_roam = mocker.MagicMock()
        mock_roam.get_references_to_page.return_value = [
            {"uid": "uid1", "string": "x" * 600},
        ]
        mocker.patch(ROAM_CLIENT_PATH, return_value=mock_roam)

        result = get_backlinks("Page")

        assert "..." in result

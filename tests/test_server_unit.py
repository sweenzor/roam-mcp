"""
Unit tests for the Roam MCP server with mocked dependencies.

These tests use pytest-mock to mock external dependencies (RoamAPI) and ensure
fast, isolated testing without requiring actual Roam API access.
"""
import pytest
from mcp_server_roam.server import (
    roam_hello_world,
    roam_get_page_markdown,
)
from mcp_server_roam.roam_api import (
    PageNotFoundException,
    RoamAPIException,
    AuthenticationException,
)


# Fixtures for mock data
@pytest.fixture
def mock_page_data_simple():
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
def mock_page_data_nested():
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
def mock_page_data_empty():
    """Page with no children blocks."""
    return {
        ":node/title": "Empty Page",
        ":block/uid": "empty-page-uid",
        ":block/children": [],
    }


# Tests for roam_hello_world
class TestRoamHelloWorld:
    """Tests for the simple hello world function."""

    def test_hello_world_default(self):
        """Test hello world with default parameter."""
        result = roam_hello_world()
        assert "Hello, World!" in result
        assert "Roam Research MCP server" in result

    def test_hello_world_custom_name(self):
        """Test hello world with custom name parameter."""
        result = roam_hello_world("Claude")
        assert "Hello, Claude!" in result
        assert "Roam Research MCP server" in result

    def test_hello_world_empty_name(self):
        """Test hello world with empty string name."""
        result = roam_hello_world("")
        assert "Hello, !" in result


# Tests for roam_get_page_markdown
class TestRoamGetPageMarkdown:
    """Tests for fetching page content as markdown."""

    def test_get_page_markdown_simple(self, mocker, mock_page_data_simple):
        """Test getting page markdown with simple structure."""
        # Mock get_roam_client to return a mock RoamAPI instance
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.return_value = mock_page_data_simple
        mock_roam_instance.process_blocks.return_value = "- First block content\n- Second block content\n"

        mocker.patch("mcp_server_roam.server.get_roam_client", return_value=mock_roam_instance)

        result = roam_get_page_markdown("Test Page")

        # Verify the API was called correctly
        mock_roam_instance.get_page.assert_called_once_with("Test Page")

        # Verify the markdown output
        assert "# Test Page\n\n" in result
        assert "- First block content\n" in result
        assert "- Second block content\n" in result

    def test_get_page_markdown_nested(self, mocker, mock_page_data_nested):
        """Test getting page markdown with nested structure."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.return_value = mock_page_data_nested
        mock_roam_instance.process_blocks.return_value = "- Top level block\n  - Second level block\n    - Third level block\n  - Another second level\n- Another top level\n"

        mocker.patch("mcp_server_roam.server.get_roam_client", return_value=mock_roam_instance)

        result = roam_get_page_markdown("Nested Page")

        # Verify structure
        assert "# Nested Page\n\n" in result
        assert "- Top level block\n" in result
        assert "  - Second level block\n" in result
        assert "    - Third level block\n" in result
        assert "  - Another second level\n" in result
        assert "- Another top level\n" in result

    def test_get_page_markdown_empty(self, mocker, mock_page_data_empty):
        """Test getting page markdown for page with no blocks."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.return_value = mock_page_data_empty
        mock_roam_instance.process_blocks.return_value = ""

        mocker.patch("mcp_server_roam.server.get_roam_client", return_value=mock_roam_instance)

        result = roam_get_page_markdown("Empty Page")

        # Should only have the title, no blocks
        assert result == "# Empty Page\n\n"

    def test_get_page_markdown_no_children_key(self, mocker):
        """Test getting page markdown when :block/children key is missing."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.return_value = {
            ":node/title": "No Children Key",
            ":block/uid": "no-children-uid",
        }

        mocker.patch("mcp_server_roam.server.get_roam_client", return_value=mock_roam_instance)

        result = roam_get_page_markdown("No Children Key")

        # Should only have the title
        assert result == "# No Children Key\n\n"
        # process_blocks should not be called
        mock_roam_instance.process_blocks.assert_not_called()


# Tests for error handling
class TestRoamGetPageMarkdownErrors:
    """Tests for error handling in roam_get_page_markdown."""

    def test_get_page_markdown_page_not_found(self, mocker):
        """Test error handling when page is not found."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.side_effect = PageNotFoundException(
            "Page with title 'Nonexistent Page' not found"
        )

        mocker.patch("mcp_server_roam.server.get_roam_client", return_value=mock_roam_instance)

        result = roam_get_page_markdown("Nonexistent Page")

        # Should return an error message, not raise an exception
        assert "Error:" in result
        assert "not found" in result
        mock_roam_instance.get_page.assert_called_once_with("Nonexistent Page")

    def test_get_page_markdown_api_error(self, mocker):
        """Test error handling when API raises a general exception."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.side_effect = RoamAPIException("API connection failed")

        mocker.patch("mcp_server_roam.server.get_roam_client", return_value=mock_roam_instance)

        result = roam_get_page_markdown("Test Page")

        # Should return an error message
        assert "Error fetching page:" in result
        assert "API connection failed" in result

    def test_get_page_markdown_authentication_error(self, mocker):
        """Test error handling for authentication errors."""
        mock_roam_instance = mocker.MagicMock()
        mock_roam_instance.get_page.side_effect = AuthenticationException(
            "Authentication error (HTTP 401): Invalid token"
        )

        mocker.patch("mcp_server_roam.server.get_roam_client", return_value=mock_roam_instance)

        result = roam_get_page_markdown("Test Page")

        assert "Error fetching page:" in result
        assert "Authentication error" in result

    def test_get_page_markdown_roam_client_init_error(self, mocker):
        """Test error handling when RoamAPI initialization fails."""
        mocker.patch(
            "mcp_server_roam.server.get_roam_client",
            side_effect=RoamAPIException("Failed to initialize RoamAPI client: Roam API token not provided")
        )

        result = roam_get_page_markdown("Test Page")

        # Should catch the initialization error
        assert "Error fetching page:" in result
        assert "Failed to initialize RoamAPI client" in result


# Integration-style tests (still mocked, but testing the full flow)
class TestRoamGetPageMarkdownIntegration:
    """Integration-style tests for the full markdown conversion flow."""

    def test_real_world_page_structure(self, mocker):
        """Test with a realistic page structure including references and todos."""
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

        mocker.patch("mcp_server_roam.server.get_roam_client", return_value=mock_roam_instance)

        result = roam_get_page_markdown("Project Planning")

        # Verify the full structure including Roam-specific syntax
        assert "# Project Planning\n\n" in result
        assert "- Project goals\n" in result
        assert "  - TODO Implement feature [[Feature A]]\n" in result
        assert "  - DONE Research options #research\n" in result
        assert "- Meeting notes from [[June 1st, 2025]]\n" in result

    def test_deeply_nested_structure(self, mocker):
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

        mocker.patch("mcp_server_roam.server.get_roam_client", return_value=mock_roam_instance)

        result = roam_get_page_markdown("Deep Nesting")

        # Verify indentation at each level
        assert "- Level 1\n" in result
        assert "  - Level 2\n" in result
        assert "    - Level 3\n" in result
        assert "      - Level 4\n" in result
        assert "        - Level 5\n" in result

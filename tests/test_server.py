"""Unit tests for Roam MCP server tools."""
from unittest.mock import MagicMock, patch

from mcp_server_roam.server import (
    roam_create_block,
    roam_get_page_markdown,
    roam_hello_world,
)


def test_roam_hello_world() -> None:
    """Test hello world tool with default and custom names."""
    # Test with default value
    result = roam_hello_world()
    assert "Hello, World!" in result

    # Test with custom name
    result = roam_hello_world("Roam")
    assert "Hello, Roam!" in result


@patch('mcp_server_roam.server.get_roam_client')
def test_roam_get_page_markdown(mock_get_client: MagicMock) -> None:
    """Test get_page_markdown tool with mocked API."""
    # Mock the RoamAPI instance and its methods
    mock_instance = MagicMock()
    mock_get_client.return_value = mock_instance
    mock_instance.get_page.return_value = {
        ":block/children": [
            {":block/string": "This is a mock implementation"},
            {":block/string": "Another test block"}
        ]
    }
    # Mock the process_blocks method to return formatted markdown
    mock_instance.process_blocks.return_value = (
        "- This is a mock implementation\n- Another test block\n"
    )

    result = roam_get_page_markdown("Test Page")
    assert "Test Page" in result
    assert "mock implementation" in result.lower()
    mock_instance.get_page.assert_called_once_with("Test Page")
    mock_instance.process_blocks.assert_called_once()


@patch('mcp_server_roam.server.get_roam_client')
def test_roam_create_block(mock_get_client: MagicMock) -> None:
    """Test create_block tool with mocked API."""
    mock_instance = MagicMock()
    mock_get_client.return_value = mock_instance
    mock_instance.create_block.return_value = {"uid": "mock-block-uid"}

    # Test with no page or title (should default to daily note)
    result = roam_create_block("Test content")
    assert "Created block" in result
    assert "Test content" in result
    mock_instance.create_block.assert_called_with("Test content", None)

    # Test with page_uid
    mock_instance.reset_mock()
    result = roam_create_block("Test content", page_uid="page123")
    assert "Created block" in result
    assert "Test content" in result
    mock_instance.create_block.assert_called_with("Test content", "page123")

    # Test with title - mock the query to find page UID
    mock_instance.reset_mock()
    mock_instance.run_query.return_value = [["found-page-uid"]]
    result = roam_create_block("Test content", title="Test Page")
    assert "Created block" in result
    assert "Test content" in result
    mock_instance.run_query.assert_called_once()
    mock_instance.create_block.assert_called_with("Test content", "found-page-uid")

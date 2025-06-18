from unittest.mock import patch, MagicMock
from mcp_server_roam.server import roam_hello_world, roam_fetch_page_by_title, roam_create_block

def test_roam_hello_world():
    # Test with default value
    result = roam_hello_world()
    assert "Hello, World!" in result
    
    # Test with custom name
    result = roam_hello_world("Roam")
    assert "Hello, Roam!" in result

@patch('mcp_server_roam.server.RoamAPI')
def test_roam_fetch_page_by_title(mock_roam_api):
    # Mock the RoamAPI instance and its get_page method
    mock_instance = MagicMock()
    mock_roam_api.return_value = mock_instance
    mock_instance.get_page.return_value = {
        ":block/children": [
            {":block/string": "This is a mock implementation"},
            {":block/string": "Another test block"}
        ]
    }
    
    result = roam_fetch_page_by_title("Test Page")
    assert "Test Page" in result
    assert "mock implementation" in result.lower()
    mock_instance.get_page.assert_called_once_with("Test Page")

@patch('mcp_server_roam.server.RoamAPI')
def test_roam_create_block(mock_roam_api):
    # Mock the RoamAPI instance and its methods
    mock_instance = MagicMock()
    mock_roam_api.return_value = mock_instance
    mock_instance.create_block.return_value = {"uid": "mock-block-uid"}
    
    # Test with no page or title (should default to daily note)
    result = roam_create_block("Test content")
    assert result["success"] is True
    assert "Test content" in result["message"]
    mock_instance.create_block.assert_called_with("Test content", None)
    
    # Test with page_uid
    mock_instance.reset_mock()
    result = roam_create_block("Test content", page_uid="page123")
    assert result["success"] is True
    assert "Test content" in result["message"]
    mock_instance.create_block.assert_called_with("Test content", "page123")
    
    # Test with title - mock the query to find page UID
    mock_instance.reset_mock()
    mock_instance.run_query.return_value = [["found-page-uid"]]
    result = roam_create_block("Test content", title="Test Page")
    assert result["success"] is True
    assert "Test content" in result["message"]
    mock_instance.run_query.assert_called_once()
    mock_instance.create_block.assert_called_with("Test content", "found-page-uid")
import pytest
from mcp_server_roam.server import roam_hello_world, roam_fetch_page_by_title, roam_create_block

def test_roam_hello_world():
    # Test with default value
    result = roam_hello_world()
    assert "Hello, World!" in result
    
    # Test with custom name
    result = roam_hello_world("Roam")
    assert "Hello, Roam!" in result

def test_roam_fetch_page_by_title():
    result = roam_fetch_page_by_title("Test Page")
    assert "Test Page" in result
    assert "mock implementation" in result.lower()

def test_roam_create_block():
    # Test with no page or title (should default to daily note)
    result = roam_create_block("Test content")
    assert result["success"] is True
    assert "Daily Note" in result["message"]
    assert "Test content" in result["message"]
    
    # Test with page_uid
    result = roam_create_block("Test content", page_uid="page123")
    assert "page123" in result["message"]
    
    # Test with title
    result = roam_create_block("Test content", title="Test Page")
    assert "Test Page" in result["message"]
#!/usr/bin/env python3
import asyncio
from mcp.server.fastmcp import FastMCP, Context
from typing import Dict, Any, List, Optional
import json

from .roam_api import RoamAPI
from .markdown_utils import parse_markdown, convert_to_roam_actions, convert_to_roam_markdown

# Initialize the MCP server
mcp = FastMCP("roam-research")

# Initialize Roam API
roam = RoamAPI()

# Define tools
@mcp.tool()
async def fetch_page_by_title(title: str) -> str:
    """Retrieve complete page contents by exact title, including all nested blocks.
    
    Args:
        title: Title of the page. For date pages, use ordinal date formats such as January 2nd, 2025
    """
    try:
        content = await roam.fetch_page_content(title)
        return content
    except Exception as e:
        raise Exception(f"Failed to fetch page: {str(e)}")

@mcp.tool()
async def import_markdown(
    content: str,
    page_uid: Optional[str] = None,
    page_title: Optional[str] = None,
    parent_uid: Optional[str] = None,
    parent_string: Optional[str] = None,
    order: str = "first"
) -> Dict[str, Any]:
    """Import nested markdown content into Roam under a specific block.
    
    Args:
        content: Nested markdown content to import
        page_uid: Optional - UID of the page containing the parent block
        page_title: Optional - Title of the page containing the parent block (ignored if page_uid provided)
        parent_uid: Optional - UID of the parent block to add content under
        parent_string: Optional - Exact string content of the parent block to add content under (must provide either page_uid or page_title)
        order: Optional - Where to add the content under the parent ("first" or "last")
    """
    if order not in ["first", "last"]:
        order = "first"
    
    try:
        # First get the page UID
        target_page_uid = page_uid
        
        if not target_page_uid and page_title:
            target_page_uid = await roam.find_page_by_title(page_title)
            
            if not target_page_uid:
                # Create the page if it doesn't exist
                await roam.create_page(page_title)
                target_page_uid = await roam.find_page_by_title(page_title)
                if not target_page_uid:
                    raise Exception(f"Failed to create page: {page_title}")
        
        # If no page specified, use today's daily page
        if not target_page_uid:
            target_page_uid = await roam.get_today_page()
        
        # Now get the parent block UID
        target_parent_uid = parent_uid
        
        if not target_parent_uid and parent_string:
            if not target_page_uid:
                raise Exception("Must provide either page_uid or page_title when using parent_string")
            
            # Find block by string match within the page
            query = f"""[:find ?uid
                      :where [?p :block/uid "{target_page_uid}"]
                             [?b :block/page ?p]
                             [?b :block/string "{parent_string}"]]"""
                             
            results = await roam.execute_query(query)
            
            if not results or len(results) == 0:
                raise Exception(f"Block with content '{parent_string}' not found on specified page")
            
            target_parent_uid = results[0][0]
        
        # If no parent specified, use page as parent
        if not target_parent_uid:
            target_parent_uid = target_page_uid
        
        # Handle multi-line content
        if "\n" in content:
            # Convert to Roam-flavored markdown
            converted_content = convert_to_roam_markdown(content)
            
            # Parse into hierarchical structure
            nodes = parse_markdown(converted_content)
            
            # Convert to actions
            actions = convert_to_roam_actions(nodes, target_parent_uid, order)
            
            # Execute batch actions
            result = await roam.batch_actions(actions)
            
            if not result:
                raise Exception("Failed to import nested markdown content")
            
            return {
                "success": True,
                "page_uid": target_page_uid,
                "parent_uid": target_parent_uid,
                "created_uids": result.get("created_uids", [])
            }
        else:
            # Simple single-line content
            await roam.create_block(target_parent_uid, content, order)
            
            return {
                "success": True,
                "page_uid": target_page_uid,
                "parent_uid": target_parent_uid
            }
    except Exception as e:
        raise Exception(f"Failed to import markdown: {str(e)}")

@mcp.tool()
async def search_by_text(
    text: str,
    page_title_uid: Optional[str] = None
) -> Dict[str, Any]:
    """Search for blocks containing specific text across all pages or within a specific page.
    
    Args:
        text: The text to search for
        page_title_uid: Optional - Title or UID of the page to search in. If not provided, searches across all pages
    """
    try:
        # Get target page UID if provided
        target_page_uid = None
        if page_title_uid:
            # Try to find by title first
            find_query = "[:find ?uid :in $ ?title :where [?e :node/title ?title] [?e :block/uid ?uid]]"
            results = await roam.execute_query(find_query, [page_title_uid])
            if results and len(results) > 0:
                target_page_uid = results[0][0]
            else:
                # Try as UID
                uid_query = f"""[:find ?uid
                              :where [?e :block/uid "{page_title_uid}"]
                                     [?e :block/uid ?uid]]"""
                results = await roam.execute_query(uid_query)
                if results and len(results) > 0:
                    target_page_uid = results[0][0]
                else:
                    raise Exception(f"Page with title/UID '{page_title_uid}' not found")
        
        # Build query based on scope
        if target_page_uid:
            query = f"""[:find ?block-uid ?block-str
                      :in $ ?search-text ?page-uid
                      :where [?p :block/uid ?page-uid]
                             [?b :block/page ?p]
                             [?b :block/string ?block-str]
                             [?b :block/uid ?block-uid]
                             [(clojure.string/includes? ?block-str ?search-text)]]"""
            results = await roam.execute_query(query, [text, target_page_uid])
            
            matches = [
                {"block_uid": uid, "content": content}
                for uid, content in results
            ]
        else:
            query = """[:find ?block-uid ?block-str ?page-title
                      :in $ ?search-text
                      :where [?b :block/string ?block-str]
                             [(clojure.string/includes? ?block-str ?search-text)]
                             [?b :block/uid ?block-uid]
                             [?b :block/page ?p]
                             [?p :node/title ?page-title]]"""
            results = await roam.execute_query(query, [text])
            
            matches = [
                {"block_uid": uid, "content": content, "page_title": page_title}
                for uid, content, page_title in results
            ]
        
        return {
            "success": True,
            "matches": matches,
            "message": f"Found {len(matches)} block(s) containing \"{text}\""
        }
    except Exception as e:
        raise Exception(f"Search failed: {str(e)}")

# Run the server
if __name__ == "__main__":
    print("Starting Roam MCP server...")
    mcp.run()

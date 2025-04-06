import httpx
from typing import Dict, List, Optional, Any, Union
import json
from datetime import datetime
import config

class RoamAPI:
    def __init__(self):
        self.token = config.ROAM_API_TOKEN
        self.graph = config.ROAM_GRAPH_NAME
        self.api_url = "https://api.roamresearch.com/api/graph"
        
    async def execute_query(self, query: str, inputs: List[Any] = None) -> List[Any]:
        """Execute a Datomic query against the Roam graph."""
        if inputs is None:
            inputs = []
            
        payload = {
            "method": "q",
            "args": [query, inputs],
            "token": self.token,
            "graph": self.graph
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, json=payload)
            response.raise_for_status()
            return response.json()
    
    async def create_page(self, title: str) -> bool:
        """Create a new page in Roam with the given title."""
        payload = {
            "method": "createPage",
            "args": [{
                "action": "create-page",
                "page": {
                    "title": title
                }
            }],
            "token": self.token,
            "graph": self.graph
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, json=payload)
            response.raise_for_status()
            return response.json()
    
    async def create_block(
        self, 
        parent_uid: str, 
        content: str, 
        order: Union[int, str] = "last"
    ) -> bool:
        """Create a new block in Roam."""
        payload = {
            "method": "createBlock",
            "args": [{
                "action": "create-block",
                "location": {
                    "parent-uid": parent_uid,
                    "order": order
                },
                "block": {
                    "string": content
                }
            }],
            "token": self.token,
            "graph": self.graph
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, json=payload)
            response.raise_for_status()
            return response.json()
    
    async def batch_actions(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute multiple actions in a single batch."""
        payload = {
            "method": "batchActions",
            "args": [{
                "action": "batch-actions",
                "actions": actions
            }],
            "token": self.token,
            "graph": self.graph
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, json=payload)
            response.raise_for_status()
            return response.json()

    async def find_page_by_title(self, title: str) -> Optional[str]:
        """Find a page UID by title."""
        query = "[:find ?uid :in $ ?title :where [?e :node/title ?title] [?e :block/uid ?uid]]"
        results = await self.execute_query(query, [title])
        
        if results and len(results) > 0:
            return results[0][0]
        return None
    
    async def get_today_page(self) -> str:
        """Get or create today's daily page."""
        # Format today's date in Roam's format: "Month Day(st/nd/rd/th), Year"
        today = datetime.now()
        months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        
        day = today.day
        if 10 <= day % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            
        date_str = f"{months[today.month - 1]} {day}{suffix}, {today.year}"
        
        # Find or create the page
        page_uid = await self.find_page_by_title(date_str)
        if not page_uid:
            await self.create_page(date_str)
            page_uid = await self.find_page_by_title(date_str)
            if not page_uid:
                raise Exception(f"Failed to create or find today's page: {date_str}")
        
        return page_uid
    
    async def fetch_page_content(self, title: str) -> str:
        """Fetch the content of a page by title."""
        # Get the page UID
        page_uid = await self.find_page_by_title(title)
        if not page_uid:
            raise ValueError(f"Page with title '{title}' not found")
        
        # Define a rule for traversing block hierarchy
        ancestor_rule = """[
            [ (ancestor ?b ?a) [?a :block/children ?b] ]
            [ (ancestor ?b ?a) [?parent :block/children ?b] (ancestor ?parent ?a) ]
        ]"""
        
        # Query for all blocks on the page
        query = """[:find ?block-uid ?block-str ?order ?parent-uid
                   :in $ % ?page-title
                   :where [?page :node/title ?page-title]
                          [?block :block/string ?block-str]
                          [?block :block/uid ?block-uid]
                          [?block :block/order ?order]
                          (ancestor ?block ?page)
                          [?parent :block/children ?block]
                          [?parent :block/uid ?parent-uid]]"""
        
        blocks = await self.execute_query(query, [ancestor_rule, title])
        
        if not blocks:
            return f"# {title}\n\n(No content found)"
        
        # Process blocks into a nested structure
        block_dict = {}
        root_blocks = []
        
        # First pass: Create all block objects
        for block_uid, block_str, order, parent_uid in blocks:
            block = {
                "uid": block_uid,
                "string": block_str,
                "order": order,
                "children": []
            }
            block_dict[block_uid] = block
            
            # If parent is the page itself, it's a root block
            if parent_uid == page_uid:
                root_blocks.append(block)
        
        # Second pass: Build parent-child relationships
        for block_uid, _, _, parent_uid in blocks:
            if parent_uid != page_uid:
                parent = block_dict.get(parent_uid)
                if parent and block_uid in block_dict:
                    parent["children"].append(block_dict[block_uid])
        
        # Sort blocks by order
        def sort_blocks(blocks):
            blocks.sort(key=lambda b: b["order"])
            for block in blocks:
                if block["children"]:
                    sort_blocks(block["children"])
        
        sort_blocks(root_blocks)
        
        # Convert to markdown
        markdown = f"# {title}\n\n"
        
        def block_to_markdown(block, level=0):
            indent = "  " * level
            md = f"{indent}- {block['string']}"
            
            if block["children"]:
                child_md = "\n".join(block_to_markdown(child, level + 1) for child in block["children"])
                md += f"\n{child_md}"
            
            return md
        
        blocks_md = "\n".join(block_to_markdown(block) for block in root_blocks)
        markdown += blocks_md
        
        return markdown

"""Interface to the Roam Research API."""
import os
import requests
import re
import logging
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

class RoamAPI:
    """Client for interacting with the Roam Research API."""
    
    def __init__(self, api_token: Optional[str] = None, graph_name: Optional[str] = None):
        """
        Initialize the Roam API client.
        
        Args:
            api_token: Roam API token. If None, reads from ROAM_API_TOKEN env var.
            graph_name: Roam graph name. If None, reads from ROAM_GRAPH_NAME env var.
        """
        self.api_token = api_token or os.getenv("ROAM_API_TOKEN")
        self.graph_name = graph_name or os.getenv("ROAM_GRAPH_NAME")
        
        if not self.api_token:
            raise ValueError("Roam API token not provided and ROAM_API_TOKEN env var not set")
        if not self.graph_name:
            raise ValueError("Roam graph name not provided and ROAM_GRAPH_NAME env var not set")
        
        # Initialize with the base URL
        self.__cache = {}
        logger.info(f"Initialized RoamAPI client for graph: {self.graph_name}")
    
    def __make_request(self, path: str, body: Dict[str, Any], method: str = "POST"):
        """
        Prepare a request to the Roam API, handling redirects and caching.
        
        Args:
            path: API endpoint path.
            body: Request body data.
            method: HTTP method to use (default: POST).
            
        Returns:
            Tuple of (url, method, headers).
        """
        if self.graph_name in self.__cache:
            base_url = self.__cache[self.graph_name]
        else:
            base_url = 'https://api.roamresearch.com'
        
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'Authorization': 'Bearer ' + self.api_token,
            'x-authorization': 'Bearer ' + self.api_token  # Include both headers as in the SDK
        }
        
        return (base_url + path, method, headers)
    
    def call(self, path: str, method: str, body: Dict[str, Any]) -> requests.Response:
        """
        Make an API call to Roam, following redirects if necessary.
        
        Args:
            path: API endpoint path.
            method: HTTP method to use.
            body: Request body data.
            
        Returns:
            Response object.
        """
        url, method, headers = self.__make_request(path, body, method)
        logger.info(f"Making {method} request to: {url}")
        logger.info(f"Request headers: {headers}")
        logger.info(f"Request body: {body}")
        
        resp = requests.post(url, headers=headers, json=body, allow_redirects=False)
        
        # Handle redirects manually to cache the new URL
        if resp.is_redirect or resp.status_code == 307:
            if 'Location' in resp.headers:
                logger.info(f"Received redirect to: {resp.headers['Location']}")
                mtch = re.search(r'https://(peer-\d+).*?:(\d+).*', resp.headers['Location'])
                if mtch is None:
                    raise Exception(f"Could not parse redirect URL: {resp.headers['Location']}")
                peer_n, port = mtch.groups()
                self.__cache[self.graph_name] = redirect_url = f'https://{peer_n}.api.roamresearch.com:{port}'
                logger.info(f"Cached redirect URL: {redirect_url}")
                return self.call(path, method, body)
            else:
                raise Exception(f"Redirect without Location header: {resp.headers}")
        
        # Handle errors
        if not resp.ok:
            logger.error(f"Error response status: {resp.status_code}")
            logger.error(f"Error response body: {resp.text}")
            if resp.status_code == 500:
                raise Exception(f'Server error (HTTP 500): {str(resp.text)}')
            elif resp.status_code == 400:
                raise Exception(f'Bad request (HTTP 400): {str(resp.text)}')
            elif resp.status_code == 401:
                raise Exception("Authentication error (HTTP 401): Invalid token or insufficient privileges")
            else:
                raise Exception(f'Service unavailable (HTTP {resp.status_code}): Your graph may not be ready yet, please retry in a few seconds.')
        
        return resp
    
    def run_query(self, query: str, args: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        Run a Datalog query on the Roam graph.
        
        Args:
            query: Datalog query string.
            args: Optional arguments for the query.
            
        Returns:
            Query results.
        """
        path = f'/api/graph/{self.graph_name}/q'
        body = {'query': query}
        if args is not None:
            body['args'] = args
        
        resp = self.call(path, 'POST', body)
        result = resp.json()
        return result.get('result', [])
    
    def pull(self, eid: str, pattern: str = "[*]") -> Dict[str, Any]:
        """
        Get an entity by its ID.
        
        Args:
            eid: Entity ID to pull.
            pattern: Pull pattern.
            
        Returns:
            Entity data.
        """
        path = f'/api/graph/{self.graph_name}/pull'
        body = {'eid': eid, 'selector': pattern}
        
        resp = self.call(path, 'POST', body)
        result = resp.json()
        return result.get('result', {})
    
    def get_references_to_page(self, page_title: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """
        Get blocks that reference a specific page (backlinks).
        
        Args:
            page_title: Title of the page to find references to
            max_results: Maximum number of references to return
            
        Returns:
            List of blocks that contain references to the page
        """
        # Query to find blocks that contain the page reference
        # Using clojure.string/includes? to search for the page title in block strings
        query = f'''[:find ?block-uid ?block-string
                     :where 
                     [?b :block/uid ?block-uid]
                     [?b :block/string ?block-string]
                     [(clojure.string/includes? ?block-string "[[{page_title}]]")]]'''
        
        try:
            results = self.run_query(query)
            references = []
            
            for result in results[:max_results]:  # Limit results
                block_uid, block_string = result
                references.append({
                    'uid': block_uid,
                    'string': block_string
                })
            
            return references
        except Exception as e:
            logger.error(f"Error finding references to {page_title}: {e}")
            return []
    
    def get_block(self, block_uid: str) -> Dict[str, Any]:
        """
        Get a block by its UID.
        
        Args:
            block_uid: UID of the block to fetch.
            
        Returns:
            Block data.
        """
        # First find the entity ID for the block
        query = f'[:find ?e :where [?e :block/uid "{block_uid}"]]'
        results = self.run_query(query)
        
        if not results or len(results) == 0:
            raise ValueError(f"Block with UID '{block_uid}' not found")
        
        # Pull the block data
        eid = results[0][0]
        return self.pull(eid)
    
    def get_page(self, page_title: str) -> Dict[str, Any]:
        """
        Get a page by its title.
        
        Args:
            page_title: Title of the page to fetch.
            
        Returns:
            Page data.
        """
        # First find the entity ID for the page
        query = f'[:find ?e :where [?e :node/title "{page_title}"]]'
        results = self.run_query(query)
        
        if not results or len(results) == 0:
            raise ValueError(f"Page with title '{page_title}' not found")
        
        # Pull the page data with a recursive pull pattern to get all nested blocks
        eid = results[0][0]
        # The ... notation means "recursively pull this pattern"
        pattern = "[* {:block/children ...}]"
        return self.pull(eid, pattern)
    
    def create_block(self, content: str, page_uid: Optional[str] = None, parent_uid: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new block in a Roam page or under a parent block.
        
        Args:
            content: Content of the block to create.
            page_uid: UID of the page to add the block to.
            parent_uid: UID of the parent block to add the block to.
            
        Returns:
            Created block data.
        """
        if not page_uid and not parent_uid:
            # Default to today's Daily Notes
            from datetime import datetime
            today = datetime.now().strftime("%m-%d-%Y")
            
            # Find the daily notes page
            query = f'[:find ?e :where [?e :node/title "{today}"]]'
            results = self.run_query(query)
            
            if not results or len(results) == 0:
                raise ValueError(f"Daily Notes page for '{today}' not found")
                
            # Get the UID
            daily_page_query = f'[:find ?uid :where [?e :node/title "{today}"] [?e :block/uid ?uid]]'
            uid_results = self.run_query(daily_page_query)
            
            if not uid_results or len(uid_results) == 0:
                raise ValueError(f"Could not find UID for daily page '{today}'")
                
            parent_uid = uid_results[0][0]
        
        # Prepare the request
        path = f'/api/graph/{self.graph_name}/write'
        
        # Create the block under the specified parent
        body = {
            'action': 'create-block',
            'location': {
                'parent-uid': parent_uid or page_uid,
                'order': 0  # Add at the beginning
            },
            'block': {
                'string': content
            }
        }
        
        resp = self.call(path, 'POST', body)
        return resp.json()
    
    def find_daily_note_format(self) -> str:
        """
        Try to find the correct date format for daily notes by testing common formats.
        
        Returns:
            The date format string that works for today's daily note
        """
        from datetime import datetime
        
        today = datetime.now()
        # Common Roam daily note formats
        formats_to_try = [
            "%B %d, %Y",     # "June 13, 2025"
            "%B %dth, %Y",   # "June 13th, 2025" 
            "%B %dst, %Y",   # "June 1st, 2025"
            "%B %dnd, %Y",   # "June 2nd, 2025"
            "%B %drd, %Y",   # "June 3rd, 2025"
            "%m-%d-%Y",      # "06-13-2025"
            "%Y-%m-%d",      # "2025-06-13"
            "%d-%m-%Y",      # "13-06-2025"
            "%m/%d/%Y",      # "06/13/2025"
            "%Y/%m/%d",      # "2025/06/13"
            "%d/%m/%Y",      # "13/06/2025"
        ]
        
        for fmt in formats_to_try:
            try:
                if fmt in ["%B %dth, %Y", "%B %dst, %Y", "%B %dnd, %Y", "%B %drd, %Y"]:
                    # Handle ordinal suffixes
                    day = today.day
                    if day in [1, 21, 31]:
                        suffix = "st"
                    elif day in [2, 22]:
                        suffix = "nd" 
                    elif day in [3, 23]:
                        suffix = "rd"
                    else:
                        suffix = "th"
                    
                    date_str = today.strftime(f"%B %d{suffix}, %Y")
                else:
                    date_str = today.strftime(fmt)
                
                logger.info(f"Trying daily note format: {date_str}")
                
                # Try to find this page
                query = f'[:find ?e :where [?e :node/title "{date_str}"]]'
                results = self.run_query(query)
                
                if results and len(results) > 0:
                    logger.info(f"Found daily note with format: {fmt} -> {date_str}")
                    return fmt
                    
            except Exception as e:
                logger.debug(f"Format {fmt} failed: {e}")
                continue
        
        # If no format worked, return default
        logger.warning("No daily note format found, using default")
        return "%m-%d-%Y"
    
    def get_daily_notes_context(self, days: int = 10, max_references: int = 10) -> str:
        """
        Get the last N days of daily notes with references TO those daily note pages.
        
        Args:
            days: Number of days to fetch (default: 10)
            max_references: Maximum references per daily note (default: 10)
            
        Returns:
            Markdown formatted context with daily notes and their backlinks
        """
        from datetime import datetime, timedelta
        
        context_parts = []
        
        # Auto-detect the daily note format
        date_format = self.find_daily_note_format()
        logger.info(f"Using daily note format: {date_format}")
        
        # Get the last N days
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            
            # Handle ordinal suffixes for formats that need them
            if date_format in ["%B %dth, %Y", "%B %dst, %Y", "%B %dnd, %Y", "%B %drd, %Y"]:
                day = date.day
                if day in [1, 21, 31]:
                    suffix = "st"
                elif day in [2, 22]:
                    suffix = "nd" 
                elif day in [3, 23]:
                    suffix = "rd"
                else:
                    suffix = "th"
                
                date_str = date.strftime(f"%B %d{suffix}, %Y")
            else:
                date_str = date.strftime(date_format)
            
            logger.info(f"Processing daily note: {date_str}")
            
            # Build this day's section
            day_content = [f"## {date_str}\n"]
            
            try:
                # Get the daily note page content
                page_data = self.get_page(date_str)
                
                # Add the daily note content
                if ":block/children" in page_data and page_data[":block/children"]:
                    daily_markdown = self._process_blocks_with_links(page_data[":block/children"], 0, set())
                    if daily_markdown.strip():
                        day_content.append("### Daily Note Content\n")
                        day_content.append(daily_markdown)
                
                # Get references TO this daily note page
                references = self.get_references_to_page(date_str, max_references)
                if references:
                    day_content.append(f"### References to {date_str} ({len(references)} found)\n")
                    for ref in references:
                        day_content.append(f"- {ref['string']}\n")
                
                # Only add if we have content
                if len(day_content) > 1:  # More than just the header
                    context_parts.append("".join(day_content))
                    logger.info(f"Added daily note: {date_str} with {len(references)} references")
                
            except ValueError as e:
                # Daily note doesn't exist for this day
                logger.debug(f"Daily note {date_str} not found: {e}")
                continue
        
        # Combine everything
        if context_parts:
            return "# Daily Notes Context\n\n" + "\n\n".join(context_parts)
        else:
            return "# Daily Notes Context\n\nNo daily notes found for the specified time range."
    
    def _process_blocks_with_links(self, blocks, depth: int, linked_pages: set) -> str:
        """
        Process blocks and extract linked page references.
        
        Args:
            blocks: List of blocks to process
            depth: Current nesting level
            linked_pages: Set to collect linked page titles
            
        Returns:
            Markdown-formatted blocks with proper indentation
        """
        result = ""
        indent = "  " * depth
        
        for block in blocks:
            # Get the block string content
            block_string = block.get(":block/string", "")
            if not block_string:  # Skip empty blocks
                continue
            
            # Extract linked pages from [[Page Name]] syntax
            page_links = re.findall(r'\[\[([^\]]+)\]\]', block_string)
            for page_link in page_links:
                linked_pages.add(page_link)
            
            # Add this block with proper indentation
            result += f"{indent}- {block_string}\n"
            
            # Process children recursively if they exist
            if ":block/children" in block and block[":block/children"]:
                result += self._process_blocks_with_links(block[":block/children"], depth + 1, linked_pages)
        
        return result
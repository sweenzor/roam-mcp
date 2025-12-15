"""Interface to the Roam Research API."""
import os
import re
import logging
from typing import Any, Optional

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def ordinal_suffix(day: int) -> str:
    """Return ordinal suffix (st, nd, rd, th) for a day number."""
    if day in (1, 21, 31):
        return "st"
    if day in (2, 22):
        return "nd"
    if day in (3, 23):
        return "rd"
    return "th"

# Load environment variables from .env file
load_dotenv()


# Custom Exception Classes
class RoamAPIException(Exception):
    """Base exception class for all Roam API errors."""
    pass


class PageNotFoundException(RoamAPIException):
    """Raised when a requested page is not found in the Roam graph."""
    pass


class BlockNotFoundException(RoamAPIException):
    """Raised when a requested block is not found in the Roam graph."""
    pass


class AuthenticationException(RoamAPIException):
    """Raised when authentication with the Roam API fails."""
    pass


class RateLimitException(RoamAPIException):
    """Raised when the Roam API rate limit is exceeded."""
    pass


class InvalidQueryException(RoamAPIException):
    """Raised when a query or request to the Roam API is invalid."""
    pass

class RoamAPI:
    """Client for interacting with the Roam Research API."""

    @staticmethod
    def _sanitize_query_input(value: str) -> str:
        """
        Sanitize user input before interpolating into Datalog queries.

        This function prevents query injection by:
        1. Escaping double quotes using EDN/Datalog standard (doubling them)
        2. Validating input doesn't contain suspicious control characters
        3. Handling edge cases like empty strings

        In EDN (Extensible Data Notation) and Datalog, double quotes in strings
        are escaped by doubling them. For example:
            Input: My "quote"
            Output: My ""quote""

        Args:
            value: The string value to sanitize

        Returns:
            Sanitized string safe for use in Datalog queries

        Raises:
            InvalidQueryException: If input contains suspicious patterns or control characters
        """
        if not isinstance(value, str):
            raise InvalidQueryException(f"Input must be a string, got {type(value).__name__}")

        # Check for null bytes and other control characters that could cause issues
        if '\x00' in value:
            raise InvalidQueryException("Input contains null bytes")

        # Check for suspicious patterns that might indicate query injection attempts
        # These patterns are unusual in normal page titles/UIDs and could indicate malicious intent
        suspicious_patterns = [
            r'\[:find',   # Datalog find clause
            r'\[:where',  # Datalog where clause
            r'\[\?[a-z]',  # Logic variables (e.g., [?e, [?b)
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                raise InvalidQueryException(f"Input contains suspicious pattern: {pattern}")

        # Escape double quotes by doubling them (EDN/Datalog standard)
        sanitized = value.replace('"', '""')

        return sanitized

    def __init__(self, api_token: Optional[str] = None, graph_name: Optional[str] = None):
        """
        Initialize the Roam API client.

        Args:
            api_token: Roam API token. If None, reads from ROAM_API_TOKEN env var.
            graph_name: Roam graph name. If None, reads from ROAM_GRAPH_NAME env var.

        Raises:
            AuthenticationException: If API token or graph name is not provided.
        """
        self.api_token = api_token or os.getenv("ROAM_API_TOKEN")
        self.graph_name = graph_name or os.getenv("ROAM_GRAPH_NAME")

        if not self.api_token:
            raise AuthenticationException("Roam API token not provided and ROAM_API_TOKEN env var not set")
        if not self.graph_name:
            raise AuthenticationException("Roam graph name not provided and ROAM_GRAPH_NAME env var not set")

        self._redirect_cache: dict[str, str] = {}
        self._daily_note_format: Optional[str] = None
        logger.info(f"Initialized RoamAPI client for graph: {self.graph_name}")

    def _mask_token(self, token: str) -> str:
        """Mask a token for logging, showing first/last 4 chars if long enough."""
        if len(token) > 8:
            return f"{token[:4]}...{token[-4:]}"
        return "***"

    def call(self, path: str, body: dict[str, Any]) -> requests.Response:
        """
        Make an API call to Roam, following redirects if necessary.

        Args:
            path: API endpoint path.
            body: Request body data.

        Returns:
            Response object.

        Raises:
            InvalidQueryException: If redirect URL cannot be parsed or redirect has no Location header.
            AuthenticationException: If authentication fails (HTTP 401).
            RateLimitException: If rate limit is exceeded (HTTP 429).
            RoamAPIException: For other API errors (HTTP 400, 500, etc.).
        """
        base_url = self._redirect_cache.get(self.graph_name, "https://api.roamresearch.com")
        url = base_url + path
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {self.api_token}",
            "x-authorization": f"Bearer {self.api_token}",
        }

        logger.info(f"Making POST request to: {url}")
        logger.info(f"Request headers: Authorization: Bearer {self._mask_token(self.api_token)}")

        resp = requests.post(url, headers=headers, json=body, allow_redirects=False)
        
        # Handle redirects manually to cache the new URL
        if resp.is_redirect or resp.status_code == 307:
            if "Location" not in resp.headers:
                raise InvalidQueryException(f"Redirect without Location header: {resp.headers}")

            location = resp.headers["Location"]
            logger.info(f"Received redirect to: {location}")

            match = re.search(r"https://(peer-\d+).*?:(\d+)", location)
            if not match:
                raise InvalidQueryException(f"Could not parse redirect URL: {location}")

            peer, port = match.groups()
            redirect_url = f"https://{peer}.api.roamresearch.com:{port}"
            self._redirect_cache[self.graph_name] = redirect_url
            logger.info(f"Cached redirect URL: {redirect_url}")
            return self.call(path, body)
        
        # Handle errors
        if not resp.ok:
            logger.error(f"Error response status: {resp.status_code}")
            logger.error(f"Error response body: {resp.text}")
            if resp.status_code == 500:
                raise RoamAPIException(f'Server error (HTTP 500): {str(resp.text)}')
            elif resp.status_code == 400:
                raise InvalidQueryException(f'Bad request (HTTP 400): {str(resp.text)}')
            elif resp.status_code == 401:
                raise AuthenticationException("Authentication error (HTTP 401): Invalid token or insufficient privileges")
            elif resp.status_code == 429:
                raise RateLimitException(f'Rate limit exceeded (HTTP 429): {str(resp.text)}')
            else:
                raise RoamAPIException(f'Service unavailable (HTTP {resp.status_code}): Your graph may not be ready yet, please retry in a few seconds.')
        
        return resp
    
    def run_query(self, query: str, args: Optional[dict[str, Any]] = None) -> list[Any]:
        """
        Run a Datalog query on the Roam graph.

        Args:
            query: Datalog query string.
            args: Optional arguments for the query.

        Returns:
            Query results.

        Raises:
            InvalidQueryException: If the query is malformed or invalid.
            RoamAPIException: If the API request fails.
        """
        path = f"/api/graph/{self.graph_name}/q"
        body = {"query": query}
        if args is not None:
            body["args"] = args

        resp = self.call(path, body)
        result = resp.json()
        return result.get('result', [])
    
    def pull(self, eid: str, pattern: str = "[*]") -> dict[str, Any]:
        """Get an entity by its ID."""
        path = f"/api/graph/{self.graph_name}/pull"
        body = {"eid": eid, "selector": pattern}
        resp = self.call(path, body)
        return resp.json().get("result", {})
    
    def get_references_to_page(self, page_title: str, max_results: int = 20) -> list[dict[str, Any]]:
        """
        Get blocks that reference a specific page (backlinks).

        Args:
            page_title: Title of the page to find references to
            max_results: Maximum number of references to return

        Returns:
            List of blocks that contain references to the page.
            Returns empty list if an error occurs during retrieval.

        Note:
            This method catches and logs RoamAPIException errors, returning an empty list
            rather than propagating the exception. This is useful for non-critical operations
            where missing references should not halt execution.
        """
        # Sanitize input to prevent query injection
        sanitized_title = self._sanitize_query_input(page_title)

        # Query to find blocks that contain the page reference
        # Using clojure.string/includes? to search for the page title in block strings
        query = f'''[:find ?block-uid ?block-string
                     :where
                     [?b :block/uid ?block-uid]
                     [?b :block/string ?block-string]
                     [(clojure.string/includes? ?block-string "[[{sanitized_title}]]")]]'''
        
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
        except RoamAPIException as e:
            logger.error(f"Error finding references to {page_title}: {e}")
            return []
    
    def get_block(self, block_uid: str) -> dict[str, Any]:
        """
        Get a block by its UID.

        Args:
            block_uid: UID of the block to fetch.

        Returns:
            Block data.

        Raises:
            BlockNotFoundException: If the block with the specified UID is not found.
            InvalidQueryException: If the query contains invalid patterns.
        """
        # Sanitize input to prevent query injection
        sanitized_uid = self._sanitize_query_input(block_uid)

        # First find the entity ID for the block
        query = f'[:find ?e :where [?e :block/uid "{sanitized_uid}"]]'
        results = self.run_query(query)
        
        if not results or len(results) == 0:
            raise BlockNotFoundException(f"Block with UID '{block_uid}' not found")
        
        # Pull the block data
        eid = results[0][0]
        return self.pull(eid)
    
    def get_page(self, page_title: str) -> dict[str, Any]:
        """
        Get a page by its title.

        Args:
            page_title: Title of the page to fetch.

        Returns:
            Page data.

        Raises:
            PageNotFoundException: If the page with the specified title is not found.
            InvalidQueryException: If the query contains invalid patterns.
        """
        # Sanitize input to prevent query injection
        sanitized_title = self._sanitize_query_input(page_title)

        # First find the entity ID for the page
        query = f'[:find ?e :where [?e :node/title "{sanitized_title}"]]'
        results = self.run_query(query)
        
        if not results or len(results) == 0:
            raise PageNotFoundException(f"Page with title '{page_title}' not found")
        
        # Pull the page data with a recursive pull pattern to get all nested blocks
        eid = results[0][0]
        # The ... notation means "recursively pull this pattern"
        pattern = "[* {:block/children ...}]"
        return self.pull(eid, pattern)
    
    def create_block(self, content: str, page_uid: Optional[str] = None, parent_uid: Optional[str] = None) -> dict[str, Any]:
        """
        Create a new block in a Roam page or under a parent block.

        Args:
            content: Content of the block to create.
            page_uid: UID of the page to add the block to.
            parent_uid: UID of the parent block to add the block to.

        Returns:
            Created block data.

        Raises:
            PageNotFoundException: If the daily notes page is not found (when neither page_uid nor parent_uid provided).
            BlockNotFoundException: If the UID for the daily page cannot be found.
            RoamAPIException: If the API request fails.
        """
        if not page_uid and not parent_uid:
            # Default to today's Daily Notes
            from datetime import datetime
            today = datetime.now().strftime("%m-%d-%Y")

            # Sanitize date string to prevent query injection
            sanitized_today = self._sanitize_query_input(today)

            # Find the daily notes page
            query = f'[:find ?e :where [?e :node/title "{sanitized_today}"]]'
            results = self.run_query(query)

            if not results or len(results) == 0:
                raise PageNotFoundException(f"Daily Notes page for '{today}' not found")

            # Get the UID
            daily_page_query = f'[:find ?uid :where [?e :node/title "{sanitized_today}"] [?e :block/uid ?uid]]'
            uid_results = self.run_query(daily_page_query)
            
            if not uid_results or len(uid_results) == 0:
                raise BlockNotFoundException(f"Could not find UID for daily page '{today}'")
                
            parent_uid = uid_results[0][0]
        
        path = f"/api/graph/{self.graph_name}/write"
        body = {
            "action": "create-block",
            "location": {"parent-uid": parent_uid or page_uid, "order": 0},
            "block": {"string": content},
        }
        resp = self.call(path, body)
        return resp.json()
    
    def find_daily_note_format(self) -> str:
        """
        Try to find the correct date format for daily notes by testing common formats.
        Uses caching to avoid re-detection on subsequent calls.

        Returns:
            The date format string that works for today's daily note
        """
        if self._daily_note_format is not None:
            return self._daily_note_format

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
                    date_str = today.strftime(f"%B %d{ordinal_suffix(today.day)}, %Y")
                else:
                    date_str = today.strftime(fmt)

                logger.info(f"Trying daily note format: {date_str}")

                # Sanitize date string to prevent query injection
                sanitized_date = self._sanitize_query_input(date_str)

                # Try to find this page
                query = f'[:find ?e :where [?e :node/title "{sanitized_date}"]]'
                results = self.run_query(query)

                if results:
                    logger.info(f"Found daily note with format: {fmt} -> {date_str}")
                    self._daily_note_format = fmt
                    return fmt

            except Exception as e:
                logger.debug(f"Format {fmt} failed: {e}")
                continue

        logger.warning("No daily note format found, using default")
        self._daily_note_format = "%m-%d-%Y"
        return self._daily_note_format
    
    def get_daily_notes_context(self, days: int = 10, max_references: int = 10) -> str:
        """
        Get the last N days of daily notes with references TO those daily note pages.

        Args:
            days: Number of days to fetch (default: 10)
            max_references: Maximum references per daily note (default: 10)

        Returns:
            Markdown formatted context with daily notes and their backlinks

        Raises:
            RoamAPIException: If there are API errors during data retrieval.
        """
        from datetime import datetime, timedelta
        
        context_parts = []
        
        # Auto-detect the daily note format
        date_format = self.find_daily_note_format()
        logger.info(f"Using daily note format: {date_format}")
        
        # Get the last N days
        for i in range(days):
            date = datetime.now() - timedelta(days=i)

            if date_format in ["%B %dth, %Y", "%B %dst, %Y", "%B %dnd, %Y", "%B %drd, %Y"]:
                date_str = date.strftime(f"%B %d{ordinal_suffix(date.day)}, %Y")
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
                    daily_markdown = self.process_blocks(page_data[":block/children"], 0, extract_links=False)
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
                
            except PageNotFoundException as e:
                # Daily note doesn't exist for this day
                logger.debug(f"Daily note {date_str} not found: {e}")
                continue
        
        # Combine everything
        if context_parts:
            return "# Daily Notes Context\n\n" + "\n\n".join(context_parts)
        else:
            return "# Daily Notes Context\n\nNo daily notes found for the specified time range."
    
    def process_blocks(self, blocks: list[dict[str, Any]], depth: int = 0,
                      extract_links: bool = False, linked_pages: Optional[set] = None) -> str:
        """
        Recursively process blocks and convert them to markdown.

        This unified function handles both simple markdown conversion and link extraction,
        eliminating code duplication between server.py and roam_api.py.

        Args:
            blocks: List of blocks to process
            depth: Current nesting level (0 = top level)
            extract_links: If True, extract [[page]] links into linked_pages set
            linked_pages: Set to collect linked page titles (required if extract_links=True)

        Returns:
            Markdown-formatted blocks with proper indentation

        Example:
            # Simple markdown conversion:
            markdown = roam.process_blocks(blocks, depth=0)

            # With link extraction:
            links = set()
            markdown = roam.process_blocks(blocks, depth=0, extract_links=True, linked_pages=links)
        """
        if extract_links and linked_pages is None:
            raise ValueError("linked_pages parameter is required when extract_links=True")

        result = ""
        indent = "  " * depth

        for block in blocks:
            # Get the block string content
            block_string = block.get(":block/string", "")
            if not block_string:  # Skip empty blocks
                continue

            # Extract linked pages from [[Page Name]] syntax if requested
            if extract_links and linked_pages is not None:
                page_links = re.findall(r'\[\[([^\]]+)\]\]', block_string)
                for page_link in page_links:
                    linked_pages.add(page_link)

            # Add this block with proper indentation
            result += f"{indent}- {block_string}\n"

            # Process children recursively if they exist
            if ":block/children" in block and block[":block/children"]:
                result += self.process_blocks(
                    block[":block/children"],
                    depth + 1,
                    extract_links=extract_links,
                    linked_pages=linked_pages
                )

        return result
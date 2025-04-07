"""Interface to the Roam Research API."""
import os
import requests
import json
import re
import logging
from typing import Any, Dict, List, Optional, Union
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
                raise Exception(f"Authentication error (HTTP 401): Invalid token or insufficient privileges")
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
        
        # Pull the page data with a specific pattern to include children and their children
        eid = results[0][0]
        pattern = "[* {:block/children [* {:block/children [*]}]}]"
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
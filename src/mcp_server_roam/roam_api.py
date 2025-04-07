"""Interface to the Roam Research API."""
import os
import requests
import json
from typing import Any, Dict, List, Optional, Union
from dotenv import load_dotenv

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
            
        self.base_url = "https://api.roamresearch.com/api/graph"
        print(f"API Token: {self.api_token[:5]}...{self.api_token[-5:]}")
        print(f"Graph Name: {self.graph_name}")
        # Try with Bearer token format
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "X-Graph": f"{self.graph_name}"  # Add graph name in X-Graph header
        }
        print(f"Authorization header: {self.headers['Authorization'][:10]}...")
        print(f"X-Graph header: {self.headers['X-Graph']}")
    
    def _make_request(self, endpoint: str, method: str = "GET", data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make a request to the Roam API.
        
        Args:
            endpoint: API endpoint to request.
            method: HTTP method to use (GET, POST, etc.).
            data: Request data for POST/PUT requests.
            
        Returns:
            JSON response from the API.
        """
        # Try to embed the graph name in the URL as seen in the error messages
        url = f"{self.base_url}/{self.graph_name}/{endpoint}"
        print(f"Making {method} request to: {url}")
        
        try:
            if method == "GET":
                response = requests.get(url, headers=self.headers)
            elif method == "POST":
                print(f"Request data: {json.dumps(data)}")
                response = requests.post(url, headers=self.headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Print response details for debugging
            print(f"Response status: {response.status_code}")
            if response.status_code >= 400:
                print(f"Error response: {response.text}")
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response text: {e.response.text}")
            raise
    
    def run_query(self, query: str, args: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        Run a Datalog query on the Roam graph.
        
        Args:
            query: Datalog query string.
            args: Optional arguments for the query.
            
        Returns:
            Query results.
        """
        data = {"query": query}
        if args:
            data["args"] = args
            
        return self._make_request("q", method="POST", data=data)
    
    def get_block(self, block_uid: str) -> Dict[str, Any]:
        """
        Get a block by its UID.
        
        Args:
            block_uid: UID of the block to fetch.
            
        Returns:
            Block data.
        """
        data = {"uid": block_uid}
        return self._make_request("pull", method="POST", data=data)
    
    def get_page(self, page_title: str) -> Dict[str, Any]:
        """
        Get a page by its title.
        
        Args:
            page_title: Title of the page to fetch.
            
        Returns:
            Page data.
        """
        # First, use a query to find the page by title
        query = '[:find (pull ?e [*]) :where [?e :node/title ?title] [(= ?title "' + page_title + '")]]'
        results = self.run_query(query)
        
        if not results or len(results) == 0:
            raise ValueError(f"Page with title '{page_title}' not found")
            
        return results[0][0]
    
    def create_block(self, content: str, page_uid: Optional[str] = None, page_title: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new block in a Roam page.
        
        Args:
            content: Content of the block to create.
            page_uid: UID of the page to add the block to. Either page_uid or page_title must be provided.
            page_title: Title of the page to add the block to. Either page_uid or page_title must be provided.
            
        Returns:
            Created block data.
        """
        data = {
            "action": "create-block",
            "block": {"string": content}
        }
        
        if page_uid:
            data["location"] = {"parent-uid": page_uid}
        elif page_title:
            data["location"] = {"page-title": page_title}
        else:
            # Default to Daily Notes
            from datetime import datetime
            today = datetime.now().strftime("%B %d, %Y")
            data["location"] = {"page-title": today}
            
        return self._make_request("write", method="POST", data=data)
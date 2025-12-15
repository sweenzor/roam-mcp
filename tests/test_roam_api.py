#!/usr/bin/env python3
"""Test script for the Roam API client.

This script tests the RoamAPI class that's modeled after the Python SDK.
"""
import json
import logging
from typing import Any

from dotenv import load_dotenv

from mcp_server_roam.roam_api import RoamAPI

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()


def print_formatted_json(data: Any) -> None:
    """Print JSON data in a readable format.

    Args:
        data: The data to print as formatted JSON.
    """
    print(json.dumps(data, indent=2))


def main() -> None:
    """Run the test script."""
    try:
        # Initialize the Roam API client
        print("\n1. Initializing Roam API client...")
        roam = RoamAPI()

        print("\n2. Running a simple Datalog query to list pages...")
        try:
            # Use a simpler query format
            query = '[:find ?title :where [?e :node/title ?title]]'
            results = roam.run_query(query)

            print("Pages in the graph:")
            if results and len(results) > 0:
                for idx, page in enumerate(results[:10], 1):  # Show at most 10 pages
                    print(f"{idx}. {page[0]}")

                # Get details for one of the pages
                if len(results) > 0:
                    first_page = results[0][0]
                    print(f"\n3. Getting details for page '{first_page}'...")

                    try:
                        page_data = roam.get_page(first_page)
                        print(f"Page details for '{first_page}':")
                        print_formatted_json(page_data)

                        # Look for blocks on this page
                        print("\n4. Looking for blocks on this page...")
                        if 'children' in page_data and page_data['children']:
                            count = len(page_data['children'])
                            print(f"Found {count} blocks on page '{first_page}'")

                            # Display the first block
                            first_block = page_data['children'][0]
                            print("\nFirst block:")
                            print_formatted_json(first_block)

                            # Get the block UID if available
                            if 'uid' in first_block:
                                block_uid = first_block['uid']
                                print(f"\n5. Getting block: UID '{block_uid}'...")

                                try:
                                    block_data = roam.get_block(block_uid)
                                    print("Block details:")
                                    print_formatted_json(block_data)
                                except Exception as e:
                                    print(f"Error fetching block details: {e}")
                        else:
                            print(f"No blocks found on page '{first_page}'")
                    except Exception as e:
                        print(f"Error fetching page details: {e}")
            else:
                print("No pages found in the graph.")
        except Exception as e:
            print(f"Error running query: {e}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()

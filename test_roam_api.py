#!/usr/bin/env python3
"""
Test script for the Roam API client.
This script demonstrates basic usage of the RoamAPI class to fetch data from a Roam graph,
focusing on Datalog queries which are more likely to work with a read-only token.
"""

import asyncio
import json
import os
from dotenv import load_dotenv
from src.mcp_server_roam.roam_api import RoamAPI

# Load environment variables from .env file
load_dotenv()

def print_formatted_json(data):
    """Print JSON data in a readable format."""
    print(json.dumps(data, indent=2))

async def main():
    """Run the test script."""
    try:
        # Initialize the Roam API client
        print("\n1. Initializing Roam API client...")
        roam = RoamAPI()
        
        # Try a Datalog query to list some pages
        print("\n2. Running a query to list pages...")
        query = '[:find ?title :where [?e :node/title ?title]]'
        
        try:
            results = roam.run_query(query)
            print("Query successful!")
            print(f"Results type: {type(results)}")
            print(f"Raw results: {results}")
            
            print("\nPages in the graph:")
            if results and isinstance(results, list) and len(results) > 0:
                for idx, page in enumerate(results[:10], 1):  # Show at most 10 pages
                    if isinstance(page, list) and len(page) > 0:
                        print(f"{idx}. {page[0]}")
                    else:
                        print(f"{idx}. {page}")
                        
                # Continue with querying blocks if we have pages
                if len(results) > 0 and isinstance(results[0], list) and len(results[0]) > 0:
                    first_page = results[0][0]
                    print(f"\n3. Querying blocks for page '{first_page}'...")
                    
                    try:
                        block_query = '[:find (pull ?b [*]) :where [?p :node/title "' + first_page + '"] [?p :block/children ?b]]'
                        block_results = roam.run_query(block_query)
                        
                        if block_results and isinstance(block_results, list) and len(block_results) > 0:
                            print(f"Found {len(block_results)} blocks on page '{first_page}'")
                            if len(block_results) > 0:
                                print("\nFirst block:")
                                print_formatted_json(block_results[0][0] if isinstance(block_results[0], list) else block_results[0])
                                
                                # Get the block UID if available
                                block_uid = None
                                if isinstance(block_results[0], list) and len(block_results[0]) > 0:
                                    first_block = block_results[0][0]
                                    if isinstance(first_block, dict) and ":block/uid" in first_block:
                                        block_uid = first_block.get(":block/uid")
                                
                                if block_uid:
                                    print(f"\n4. Getting details for block with UID: {block_uid}")
                                    try:
                                        block_data = roam.get_block(block_uid)
                                        print("Block details:")
                                        print_formatted_json(block_data)
                                    except Exception as e:
                                        print(f"Error fetching block: {e}")
                        else:
                            print(f"No blocks found for page '{first_page}'")
                            
                            # Let's try a more general query to find any blocks
                            print("\n3b. Running a query to find any blocks...")
                            try:
                                any_block_query = '[:find (pull ?b [:block/string :block/uid]) :where [?b :block/string ?s]]'
                                any_blocks = roam.run_query(any_block_query)
                                
                                if any_blocks and isinstance(any_blocks, list) and len(any_blocks) > 0:
                                    print(f"Found {len(any_blocks)} blocks in the graph (showing first 5):")
                                    for idx, block in enumerate(any_blocks[:5], 1):
                                        print(f"{idx}. {block[0] if isinstance(block, list) else block}")
                                else:
                                    print("No blocks found in the graph.")
                            except Exception as e:
                                print(f"Error running general block query: {e}")
                                
                    except Exception as e:
                        print(f"Error querying blocks: {e}")
            else:
                print("No pages found or unexpected results format:", results)
        except Exception as e:
            print(f"Query failed: {e}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
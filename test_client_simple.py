#!/usr/bin/env python3
import requests
import json

# Base URL for the MCP server
base_url = "http://localhost:8000"

# List available tools
response = requests.get(f"{base_url}/tools")
print("Available tools:")
print(json.dumps(response.json(), indent=2))

# Call the hello_world tool
payload = {"name": "Simple Tester"}
response = requests.post(f"{base_url}/tools/hello_world/run", json=payload)
print("\nTool response:")
print(response.json())
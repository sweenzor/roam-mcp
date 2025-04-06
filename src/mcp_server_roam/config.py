import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API token and graph name from environment variables
ROAM_API_TOKEN = os.getenv("ROAM_API_TOKEN")
ROAM_GRAPH_NAME = os.getenv("ROAM_GRAPH_NAME")

# Validate environment variables
if not ROAM_API_TOKEN or not ROAM_GRAPH_NAME:
    # For testing purposes, use placeholders
    ROAM_API_TOKEN = "placeholder_token"
    ROAM_GRAPH_NAME = "placeholder_graph"
    print("Warning: Using placeholder values for ROAM_API_TOKEN and ROAM_GRAPH_NAME")
    print("Set these values in a .env file for real usage")

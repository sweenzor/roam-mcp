import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API token and graph name from environment variables
ROAM_API_TOKEN = os.getenv("ROAM_API_TOKEN")
ROAM_GRAPH_NAME = os.getenv("ROAM_GRAPH_NAME")

# Validate environment variables
if not ROAM_API_TOKEN or not ROAM_GRAPH_NAME:
    missing_vars = []
    if not ROAM_API_TOKEN:
        missing_vars.append("ROAM_API_TOKEN")
    if not ROAM_GRAPH_NAME:
        missing_vars.append("ROAM_GRAPH_NAME")
    
    error_message = (
        f"Missing required environment variables: {', '.join(missing_vars)}\n\n"
        "Please set these variables in a .env file or in your environment."
    )
    
    raise ValueError(error_message)
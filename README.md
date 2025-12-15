# MCP Server for Roam Research

A Model Context Protocol (MCP) server that provides programmatic access to Roam Research functionality via LLMs.

## Installation

```bash
# Clone and install dependencies
uv sync
```

## Configuration

Set environment variables for Roam API access:

```bash
export ROAM_API_TOKEN=your-api-token
export ROAM_GRAPH_NAME=your-graph-name
```

Or create a `.env` file in the project root:

```
ROAM_API_TOKEN=your-api-token
ROAM_GRAPH_NAME=your-graph-name
```

## Usage

### Command Line

```bash
# Run the MCP server
uv run python -m mcp_server_roam

# With verbose logging
uv run mcp-server-roam -v
```

### Claude Desktop Integration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "roam": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/roam-mcp",
        "run",
        "python",
        "-m",
        "mcp_server_roam"
      ],
      "env": {
        "ROAM_API_TOKEN": "your-roam-api-token",
        "ROAM_GRAPH_NAME": "your-graph-name"
      }
    }
  }
}
```

### Development Mode

Run with MCP Inspector for interactive testing:

```bash
uv run mcp dev
```

## Available Tools

| Tool | Description |
|------|-------------|
| `roam_hello_world` | Simple greeting for testing connectivity |
| `roam_get_page_markdown` | Retrieve page content as markdown (unlimited nesting) |
| `roam_create_block` | Create a new block in a Roam page |
| `roam_context` | Get daily notes with backlinks for context |
| `roam_debug_daily_notes` | Debug daily note format detection |

### Key Features

- **Daily Note Context**: `roam_context` fetches recent daily notes + all blocks that reference them
- **Auto-detection**: Automatically detects daily note formats (e.g., "June 13th, 2025", "06-13-2025")
- **Recursive Processing**: Handles unlimited block nesting depth
- **Error Handling**: Graceful handling of missing pages and API errors

## Development

```bash
# Run unit tests
uv run pytest

# Run e2e tests (requires API credentials)
ROAM_API_TOKEN=xxx ROAM_GRAPH_NAME=xxx uv run pytest tests/test_e2e.py -v

# Format code
uv run black src tests

# Type check
uv run pyright

# Lint
uv run ruff check src tests
```

> **Note**: Roam API has a 50 requests/minute rate limit.

## License

MIT

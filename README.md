# MCP Server for Roam Research

A Model Context Protocol (MCP) server that provides programmatic access to Roam Research functionality via LLMs.

## Installation

```bash
# Create and activate a virtual environment
uv venv

# Install the package in development mode
uv pip install -e ".[dev]"
```

## Usage

### Command Line

Run the MCP server directly:

```bash
# With standard logging
uv run mcp-server-roam

# With verbose logging
uv run mcp-server-roam -v

# With debug logging
uv run mcp-server-roam -vv
```

### Development

You can run the server in development mode with the MCP Inspector:

```bash
uv run mcp dev src/mcp_server_roam/server.py
```

### Installation in Claude Desktop

To use the server with Claude Desktop:

```bash
uv run mcp install src/mcp_server_roam/server.py
```

## Available Tools

- `roam_hello_world`: Basic greeting tool for testing
- `roam_fetch_page_by_title`: Retrieve a page's content by title
- `roam_create_block`: Create a new block in a Roam page

## Development

```bash
# Run tests
uv run pytest

# Format code
uv run black src tests

# Type check
uv run pyright

# Lint
uv run ruff check src tests
```

## License

MIT
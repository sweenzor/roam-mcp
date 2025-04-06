# MCP Server for Roam Research

An MCP (Model Context Protocol) server that provides access to Roam Research's functionality through a standardized interface for AI assistants.

## Installation

```bash
# Create and activate a virtual environment
uv venv

# Install the package in development mode
uv pip install -e ".[dev]"
```

## Usage

### Running in Development Mode

You can run the server in development mode with the MCP Inspector:

```bash
uv run mcp dev src/mcp_server_roam/server.py
```

### Installing in Claude Desktop

To use the server with Claude Desktop:

```bash
uv run mcp install src/mcp_server_roam/server.py
```

## Development

- Format code: `uv run black src tests`
- Type check: `uv run mypy src`
- Lint: `uv run ruff check src tests`
- Run tests: `uv run pytest`
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

- Use `uv` for package management

## Project Overview
This is an MCP (Model Context Protocol) server for Roam Research, allowing LLMs to interact with Roam's knowledge graph data structure. Based on a JavaScript example implementation (`reference/roam-research-mcp-js`), we're creating a Python version using the MCP Python SDK to enable AI assistants to access and manipulate Roam Research data.

## Build and Development Commands
- Package management: Use `uv` for all Python package operations
- Setup environment: `uv venv`
- Install dependencies: `uv pip install -e ".[dev]"`
- Run server: `uv run python -m mcp_server_roam`
- Run tests: `uv run pytest`
- Run single test: `uv run pytest tests/test_file.py::test_function_name -v`
- Run specific test file: `uv run python -m tests.test_roam_api`
- Format code: `uv run black src tests`
- Type check: `uv run mypy src`
- Lint: `uv run ruff check src tests`
- MCP development mode: `uv run mcp dev`
- MCP install to Claude Desktop: `uv run mcp install`
- Test client: `python test_client.py`

## Code Style Guidelines
- PEP 8 compliant with Black formatting (88-character line length)
- Use type hints for all function parameters and return values
- Use Google-style docstrings with parameter types and return values
- Import order: standard library, third-party packages, local modules
- Variable naming: snake_case for variables/functions, PascalCase for classes
- Error handling: Use specific exception types, document in docstrings
- Async functions for operations that interact with the Roam API

## Project Structure
- `/src/mcp_server_roam/` - Main module directory
  - `__init__.py` - Package initialization and CLI entry point with Click
  - `__main__.py` - Entry point for direct module execution
  - `server.py` - MCP server implementation using mcp.server.Server
  - `roam_api.py` - Interface to Roam Research API
- `/tests/` - Test directory
  - `__init__.py` - Test package initialization
  - `test_server.py` - Unit tests for server functionality
  - `test_client.py` - Script for programmatically testing the MCP server
  - `test_roam_api.py` - Tests for the Roam API client
  - `test_mcp_tools.py` - Tests for the MCP server tools
- `pyproject.toml` - Project metadata, dependencies, and build settings
- `.env` - Environment variables for Roam API token and graph name

## MCP Server Implementation
- Uses MCP Server API (`from mcp.server import Server`)
- Handles both stdin/stdout and SSE transports
- Initializes Roam API client with environment variables
- Uses Pydantic models for tool input validation
- Command-line interface with Click
- Uses dotenv for loading environment variables
- Server implementation follows the pattern from `reference/example-python-git-mcp-server`

## Roam API Client
- Based on the implementation in `reference/roam-python-sdk/roam_client/client.py`
- Handles API authentication with both 'Authorization' and 'x-authorization' headers
- Manages redirects from the main Roam API endpoint to peer nodes
- Supports Datalog queries, entity pulls, and write operations
- Uses a pull pattern to retrieve nested page/block content
- Handles error responses from the Roam API

## Roam Research Data Model
- **Blocks**: Basic unit of Roam data with unique 9-character UIDs
  - Properties: `:block/string`, `:block/uid`, `:block/children`, `:create/time`, `:edit/time`
  - Parent-child relationships form a hierarchical tree structure
- **Pages**: Collections of blocks with unique title strings
  - Properties: `:node/title`, `:block/children`, `:create/time`, `:edit/time`
  - Automatically created when referenced with `[[...]]` syntax
- **Entity-Attribute-Value (EAV) Storage**:
  - Everything in Roam is an entity with a numeric ID (`:db/id`)
  - Attributes have namespaces (e.g., `:block/string`, `:node/title`)
  - Queried using Datalog patterns

## Key Tool Implementations
Currently implemented tools:

1. `roam_hello_world`: Simple greeting tool for testing
   - Input: name (optional)
   - Output: Hello message

2. `roam_fetch_page_by_title`: Fetch page content with hierarchical structure
   - Input: page title
   - Output: Markdown representation with nested blocks
   - Simplified version with basic formatting

3. `roam_get_page_markdown`: Retrieve page content in clean markdown format
   - Input: page title
   - Output: Markdown representation with properly indented blocks
   - Recursively handles blocks at any nesting depth

4. `roam_create_block`: Add blocks to pages or under parent blocks
   - Input: content text, optional page uid or title
   - Output: Created block UID and confirmation

Future tools to consider:
- `roam_create_page`: Create new pages with optional content
- `roam_import_markdown`: Import nested markdown content
- `roam_add_todo`: Add todo items to daily pages
- `roam_search_by_text`: Search blocks by text content
- `roam_search_for_tag`: Search for blocks with specific tags
- `roam_update_block`: Update block content
- `roam_datomic_query`: Execute Datalog queries on the Roam graph

## Datalog Queries
Roam uses Datalog for querying its graph database. Key aspects:
- Basic query format: `[:find ?variables :where [conditions]]`
- Common block attributes:
  - `:block/uid`: Unique block identifier
  - `:block/string`: Block content
  - `:block/children`: Child blocks
  - `:block/parents`: List of ancestor blocks
  - `:create/time`, `:edit/time`: Creation and edit timestamps
- Common page attributes:
  - `:node/title`: Page title
- Query patterns:
  - Get blocks by content: `[?b :block/string ?content]`
  - Get pages by title: `[?p :node/title ?title]`
  - Search for text: `[(clojure.string/includes? ?string "search term")]`
  - Get block children: `[?p :block/children ?c]`
- Pull patterns for data retrieval: `[:find (pull ?e [*]) :where ...]`
- Recursive pull patterns: `[* {:block/children [* {:block/children [*]}]}]`

## Configuration and Authentication
- Use environment variables for API token and graph name:
  - `ROAM_API_TOKEN`: Roam Research API token
  - `ROAM_GRAPH_NAME`: Name of the Roam graph to access
- Support .env file for local development (via python-dotenv)
- Validate environment variables on startup
- Handle authentication errors gracefully
- API authentication requires both headers:
  - `Authorization: Bearer <token>`
  - `x-authorization: Bearer <token>`

## Error Handling
- Handle API errors with appropriate HTTP status codes
- Gracefully handle redirects to peer nodes
- Provide clear error messages in tool outputs
- Use try/except blocks to prevent tool failures from crashing the server
- Add logging to help debug API interactions
- Handle cases where pages or blocks are not found

## Testing
- Unit tests for tool implementations
- Integration tests via test_client.py
- MCP Inspector for interactive testing
- Manual verification with actual Roam graph data
- Test page retrieval with different nesting levels
- Test error handling with invalid inputs

## Deployment
- For development: `uv run mcp dev`
- For Claude Desktop: `uv run mcp install`
- Support environment variables via command line: `uv run mcp install -v ROAM_API_TOKEN=xxx -v ROAM_GRAPH_NAME=xxx`
- Support .env file for environment variables: `uv run mcp install -f .env`

## Claude Desktop Configuration
To use this MCP server with Claude Desktop, add the following configuration to Claude Desktop's config file (located at `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
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
```

Replace `/path/to/roam-mcp` with the absolute path to your repository, and update the environment variables with your actual Roam API credentials.

## References
- Example Python Git MCP Server: `reference/example-python-git-mcp-server/`
- Roam Python SDK: `reference/roam-python-sdk/`
- MCP Python SDK Documentation: https://modelcontextprotocol.io
- Roam Research API Documentation: https://roamresearch.com/#/app/developer-documentation/
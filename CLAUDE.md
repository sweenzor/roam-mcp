# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

- Use `uv` for package management

## Project Overview
This is an MCP (Model Context Protocol) server for Roam Research, allowing LLMs to interact with Roam's knowledge graph data structure. Based on a JavaScript example implementation (`reference/roam-research-mcp-js`), we're creating a Python version using the MCP Python SDK to enable AI assistants to access and manipulate Roam Research data.

## Build and Development Commands
- Package management: Use `uv` for all Python package operations
- Setup environment: `uv sync` (creates venv and installs all dependencies)
- Run server: `uv run python -m mcp_server_roam`
- Run tests: `uv run pytest`
- Run single test: `uv run pytest tests/test_file.py::test_function_name -v`
- Run e2e tests: `ROAM_API_TOKEN=xxx ROAM_GRAPH_NAME=xxx uv run pytest tests/test_e2e.py -v`
- Run tests with coverage: `uv run pytest --cov=src --cov-report=term --cov-report=html`
- Format code: `uv run black src tests`
- Type check: `uv run mypy src`
- Lint: `uv run ruff check src tests`
- MCP development mode: `uv run mcp dev`
- MCP install to Claude Desktop: `uv run mcp install`

**Pre-commit checklist**: Always run the full test suite (`uv run pytest`) before making any commits to ensure no regressions are introduced

**Note**: Roam API has a 50 requests/minute rate limit. E2E tests are consolidated to stay under this limit.

## Code Style Guidelines
- PEP 8 compliant with Black formatting (88-character line length)
- Use type hints for all function parameters and return values
- Keep docstrings concise - one-line descriptions preferred for simple functions
- Import order: standard library, third-party packages, local modules
- Variable naming: snake_case for variables/functions, PascalCase for classes
- Error handling: Use specific exception types from `roam_api.py`
- Prefer simplicity over abstraction - avoid unnecessary indirection

## Project Structure
- `/src/mcp_server_roam/` - Main module directory
  - `__init__.py` - Package initialization and CLI entry point with Click
  - `__main__.py` - Entry point for direct module execution
  - `server.py` - MCP server implementation using mcp.server.Server
  - `roam_api.py` - Interface to Roam Research API
- `/tests/` - Test directory
  - `test_server.py` - Basic unit tests for server tools
  - `test_server_unit.py` - Comprehensive unit tests with mocking
  - `test_e2e.py` - End-to-end tests (require API credentials)
  - `test_client.py` - MCP client integration test
  - `test_mcp_tools.py` - MCP server tools integration test
- `/reference/` - Reference implementations and documentation
  - `example-python-git-mcp-server/` - Example MCP server (pattern reference)
  - `example-roam-research-mcp-js/` - JavaScript Roam MCP (original inspiration)
  - `roam-python-sdk/` - Roam Python SDK (API client reference)
  - `readme-mcp-python-sdk.md` - MCP Python SDK documentation
  - `roam-research-general-info.md` - Roam Research background info
- `/specs/` - Feature specifications
  - `semantic-search.md` - Planned semantic search feature spec
- `pyproject.toml` - Project metadata, dependencies, and build settings
- `.env` - Environment variables for Roam API token and graph name (not in git)

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

2. `roam_get_page_markdown`: Retrieve page content in clean markdown format
   - Input: page title
   - Output: Markdown representation with properly indented blocks
   - Recursively handles blocks at any nesting depth

3. `roam_create_block`: Add blocks to pages or under parent blocks
   - Input: content text, optional page uid or title
   - Output: Confirmation message with block UID

4. `roam_context`: Get daily notes with their backlinks for comprehensive context
   - Input: days (default: 10), max_references (default: 10)
   - Output: Markdown with daily note content + blocks that reference each daily note
   - Auto-detects daily note formats (June 13th, 2025 vs 06-13-2025 etc.)
   - Memory optimized with configurable limits

5. `roam_debug_daily_notes`: Debug tool for daily note format detection
   - Input: none
   - Output: Shows detected daily note format and tests recent daily notes
   - Useful for troubleshooting date format issues

Future tools to consider:
- `roam_create_page`: Create new pages with optional content
- `roam_import_markdown`: Import nested markdown content
- `roam_add_todo`: Add todo items to daily pages
- `roam_search_by_text`: Search blocks by text content
- `roam_search_for_tag`: Search for blocks with specific tags
- `roam_update_block`: Update block content
- `roam_delete_block`: Delete blocks by UID
- `roam_datomic_query`: Execute custom Datalog queries on the Roam graph
- `roam_get_block_references`: Get all blocks that reference a specific block
- `roam_export_graph`: Export entire graph or subsets in various formats

## Daily Notes Context Tool
The `roam_context` tool is a powerful feature for understanding your recent work patterns and connected topics:

### Features
- **Auto-detection**: Automatically detects your Roam's daily note format (June 13th, 2025, 06-13-2025, etc.)
- **Backlinks**: Finds all blocks that reference each daily note page (not content from daily notes)
- **Memory optimized**: Configurable limits to handle large datasets without memory issues
- **Flexible timeframes**: Fetch 1-30 days of context with configurable reference limits

### Usage Examples
- `roam_context`: Default - last 10 days, up to 10 references per day
- `roam_context(days=3)`: Last 3 days with default reference limit
- `roam_context(days=7, max_references=20)`: Last week with more references per day

### Output Format
```markdown
# Daily Notes Context

## June 13th, 2025

### Daily Note Content
- Your actual daily note bullets
  - Nested content

### References to June 13th, 2025 (5 found)
- Block from project page mentioning [[June 13th, 2025]]
- Meeting notes referencing [[June 13th, 2025]]
- Todo scheduled for [[June 13th, 2025]]
```

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
- **Unit tests**: `test_server.py`, `test_server_unit.py` - run without API credentials
- **E2E tests**: `test_e2e.py` - require ROAM_API_TOKEN and ROAM_GRAPH_NAME env vars
- E2E tests auto-skip when credentials not available
- MCP Inspector for interactive testing: `uv run mcp dev`
- **Coverage targets**: Aim for >80% code coverage
- Use `pytest-cov` for coverage reporting

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
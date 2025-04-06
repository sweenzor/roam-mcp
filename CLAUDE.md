# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
This is an MCP (Model Context Protocol) server for Roam Research, allowing LLMs to interact with Roam's knowledge graph data structure. Based on a JavaScript example implementation (`reference/roam-research-mcp-js`), we're creating a Python version using the MCP Python SDK to enable AI assistants to access and manipulate Roam Research data.

## Build and Development Commands
- Package management: Use `uv` for all Python package operations
- Setup environment: `uv venv`
- Install dependencies: `uv pip install -e ".[dev]"`
- Run server: `uv run python src/mcp_server_roam/server.py`
- Run tests: `uv run pytest`
- Run single test: `uv run pytest tests/path/to/test_file.py::test_function_name -v`
- Format code: `uv run black src tests`
- Type check: `uv run mypy src`
- Lint: `uv run ruff check src tests`
- MCP development mode: `uv run mcp dev src/mcp_server_roam/server.py`
- MCP install to Claude Desktop: `uv run mcp install src/mcp_server_roam/server.py`

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
  - `server.py` - MCP server implementation with FastMCP
  - `roam_api.py` - Interface to Roam Research API
  - `markdown_utils.py` - Markdown processing utilities
  - `/tools/` - Tool implementations for Roam operations
  - `/search/` - Search implementations for querying Roam data
  - `/config/` - Environment and configuration handling

## Roam Research Data Model
- **Blocks**: Basic unit of Roam data with unique 9-character IDs (nanoid.js format)
  - Properties: string (content), uid, children, create-time, edit-time, heading, text-align
  - Parent-child relationships form a hierarchical tree structure
- **Pages**: Collections of blocks with unique title strings
  - Properties: title, children, create-time, edit-time
  - Automatically created when referenced with `[[...]]` syntax
- **Linking**: Bi-directional links between pages and blocks
  - Page references: `[[Page Title]]`
  - Block references: `((Block_ID))`
  - Block embeds: `{{embed: ((Block_ID))}}`

## MCP Server Implementation
- Use FastMCP for server implementation: `from mcp.server.fastmcp import FastMCP`
- Initialize Roam API client in server lifespan function
- Configure environment variables for Roam API token and graph name
- Support both stdio and SSE transports
- Resources expose Roam data to LLMs (read-only endpoints)
- Tools provide functionality for LLMs to interact with Roam data

## Key Tool Implementations
Based on the JavaScript example, implement these tools:
1. `roam_fetch_page_by_title`: Fetch page content with resolved references
   - Input: page title
   - Output: Markdown representation with hierarchical structure
   - Resolve block references recursively (up to 4 levels deep)
2. `roam_create_page`: Create new pages with optional content
   - Input: title, optional array of block content with nesting levels
   - Output: Created page UID
3. `roam_create_block`: Add blocks to pages (default to today's daily page)
   - Input: content text, optional page uid or title
   - Output: Created block UID and parent UID
4. `roam_import_markdown`: Import nested markdown content
   - Input: markdown content, parent block identifiers
   - Process hierarchical structure and convert to Roam blocks
5. `roam_add_todo`: Add todo items to daily pages
   - Input: array of todo items
   - Output: Created block UIDs
6. `roam_create_outline`: Create hierarchical outlines
   - Input: array of outline items with text and level
   - Output: Created block UIDs
7. `roam_search_block_refs`: Search for block references
   - Input: optional block UID, optional page title/UID
   - Output: Matching blocks with context
8. `roam_search_by_text`: Search blocks by text content
   - Input: search text, optional page scope
   - Output: Matching blocks with context
9. `roam_search_for_tag`: Search for blocks with specific tags
   - Input: primary tag, optional secondary tag, optional page scope
   - Output: Matching blocks with context
10. `roam_update_block`: Update block content
    - Input: block UID, new content or transform pattern
    - Output: Updated content
11. `roam_search_hierarchy`: Navigate parent-child relationships
    - Input: parent or child UID, max depth
    - Output: Related blocks with depth information
12. `roam_datomic_query`: Execute Datalog queries on the Roam graph
    - Input: Datalog query string, optional parameters
    - Output: Query results

## Datalog Queries
Roam uses Datalog for querying its graph database. Key aspects:
- Basic query format: `[:find ?variables :where [conditions]]`
- Common block attributes:
  - `:block/uid`: Unique block identifier
  - `:create/time`, `:edit/time`: Creation and edit timestamps
  - `:block/string`: Block content
  - `:block/parents`: List of ancestor blocks
- Common page attributes:
  - `:node/title`: Page title
- Query patterns:
  - Get blocks by content: `[?b :block/string ?content]`
  - Get pages by title: `[?p :node/title ?title]`
  - Search for text: `[(clojure.string/includes? ?string "search term")]`
  - Get block children: `[?p :block/children ?c]`
- Use Pull patterns for recursive data retrieval

## Markdown Utils
Implement conversion between standard markdown and Roam-flavored markdown:
- Parse hierarchical markdown structure (headings, bullet points, indentation)
- Convert block references (`((UID))`) and embeds (`{{embed: ((UID))}}`)
- Handle Roam-specific syntax:
  - Todo items: `- [ ]` → `{{[[TODO]]}}`
  - Completed items: `- [x]` → `{{[[DONE]]}}`
  - Tables: Convert markdown tables to Roam's `{{table}}` format
  - Highlights: `==text==` → `^^text^^`
  - Italics: `*text*` → `__text__`
- Preserve block relationships when importing

## Search Implementation
Create class-based search handlers for different query types:
- `TextSearchHandler`: Find blocks containing specific text
- `TagSearchHandler`: Find blocks with specific tags
- `BlockRefSearchHandler`: Find block references
- `HierarchySearchHandler`: Navigate parent-child relationships
- `StatusSearchHandler`: Find todo/done items
- `DatomicQueryHandler`: Execute custom Datalog queries
- Use abstraction layer over query engine for modularity

## Configuration and Authentication
- Use environment variables for API token and graph name:
  - `ROAM_API_TOKEN`: Roam Research API token
  - `ROAM_GRAPH_NAME`: Name of the Roam graph to access
- Support .env file for local development
- Validate environment variables on startup
- Handle authentication errors gracefully

## Error Handling
- Create custom exception types for different error categories:
  - `RoamAPIError`: Errors from the Roam API
  - `PageNotFoundError`: Page title doesn't exist
  - `BlockNotFoundError`: Block UID doesn't exist
  - `InvalidQueryError`: Problems with Datalog queries
  - `MarkdownParseError`: Issues parsing markdown
- Provide detailed error messages with suggestions when possible
- Map errors to appropriate MCP error codes

## Testing Strategy
- Unit tests for individual components:
  - `markdown_utils.py`: Test parsing and conversion functions
  - Search handlers: Test query construction and result formatting
  - Tool implementations: Test request handling and response formatting
- Integration tests for Roam API interactions
- Mock Roam API responses for testing
- Test edge cases: empty graphs, malformed blocks, permission issues
- Provide fixtures for commonly used test data

## Deployment
- For development: `mcp dev src/mcp_server_roam/server.py`
- For Claude Desktop: `mcp install src/mcp_server_roam/server.py`
- Support environment variables via command line: `mcp install -v ROAM_API_TOKEN=xxx -v ROAM_GRAPH_NAME=xxx`
- Support .env file for environment variables: `mcp install -f .env`

## Resources
- [Roam Research API Documentation](https://roamresearch.com/#/app/developer-documentation/)
- [MCP Python SDK Documentation](https://modelcontextprotocol.io)
- [Roam Import JSON Schema](reference/roam-research-mcp-js/Roam%20Import%20JSON%20Schema.md)
- [Roam Datalog Cheatsheet](reference/roam-research-mcp-js/Roam_Research_Datalog_Cheatsheet.md)
- [JavaScript Reference Implementation](reference/roam-research-mcp-js/)
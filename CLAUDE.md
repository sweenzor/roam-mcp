# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
This is an MCP (Model Context Protocol) server for Roam Research, allowing LLMs to interact with Roam's knowledge graph data structure. Based on a JavaScript example implementation (`documentation/roam-research-mcp-js`), we're creating a Python version using the MCP Python SDK.

## Build and Development Commands
- Package management: Use `uv` for all Python package operations
- Install dependencies: `uv pip install -e ".[dev]"`
- Run server: `uv run python src/mcp_server_roam/server.py`
- Run tests: `uv run pytest`
- Run single test: `uv run pytest tests/path/to/test_file.py::test_function_name -v`
- Format code: `uv run black src tests`
- Type check: `uv run mypy src`
- Lint: `uv run ruff check src tests`

## Code Style Guidelines
- PEP 8 compliant with Black formatting (88-character line length)
- Use type hints for all function parameters and return values
- Use Google-style docstrings with parameter types and return values
- Import order: standard library, third-party packages, local modules
- Variable naming: snake_case for variables/functions, PascalCase for classes
- Error handling: Use specific exception types, document in docstrings

## Project Structure
- `/src/mcp_server_roam/` - Main module directory
  - `server.py` - MCP server implementation
  - `roam_api.py` - Interface to Roam Research API
  - `markdown_utils.py` - Markdown processing utilities
  - `/tools/` - Tool implementations for Roam operations
  - `/search/` - Search implementations for querying Roam data

## Roam Research Integration
- Blocks are the basic unit of Roam data, each with a unique ID (9-character nanoid.js format)
- Pages are collections of blocks with a unique title
- Block hierarchy follows a tree structure (parent-child relationships)
- Bi-directional linking connects pages and blocks using `[[...]]` syntax
- Block references use `((Block_ID))` format
- Block embeds use `{{embed: ((Block_ID))}}` format

## MCP Server Implementation
- Use FastMCP for server implementation: `from mcp.server.fastmcp import FastMCP`
- Resources expose Roam data to LLMs (read-only, similar to GET endpoints)
- Tools provide functionality for LLMs to interact with Roam data
- Resource URIs should follow patterns like `roam://{graph_name}/{page_title}`
- Handle error cases gracefully, especially for non-existent pages or blocks
- Use appropriate authentication for Roam API access

## Key Tool Implementations
Based on the JavaScript example, implement these tools:
1. `roam_fetch_page_by_title`: Fetch page content with resolved references
2. `roam_create_page`: Create new pages with optional content
3. `roam_create_block`: Add blocks to pages (default to today's daily page)
4. `roam_import_markdown`: Import nested markdown content
5. `roam_add_todo`: Add todo items to daily pages
6. `roam_create_outline`: Create hierarchical outlines
7. `roam_search_block_refs`: Search for block references
8. `roam_search_by_text`: Search blocks by text content
9. `roam_search_for_tag`: Search for blocks with specific tags
10. `roam_update_block`: Update block content
11. `roam_search_hierarchy`: Navigate parent-child relationships
12. `roam_datomic_query`: Execute Datalog queries on the Roam graph

## Markdown Utils
- Implement conversion between standard markdown and Roam-flavored markdown
- Support hierarchical parsing of markdown structure
- Handle Roam-specific syntax like block references and embeds
- Implement table conversion to Roam format
- Support todo item conversion (`- [ ]` to `{{[[TODO]]}}`)

## Search Implementations
- Create a modular search system for different query types
- Support Datalog queries for advanced data retrieval
- Implement case-insensitive page title matching
- Support searching within pages or across the entire graph
- Include parent/child relationship navigation

## Roam Data Structure (JSON Schema)
- Pages require a "title" field (string)
- Blocks require a "string" field (content) 
- "uid" field preserves block references (9-character string)
- "children" field contains nested blocks (array)
- Optional metadata: "create-time", "edit-time", "heading", "text-align"

## Configuration
- Use environment variables for API token and graph name:
  - `ROAM_API_TOKEN`: Roam Research API token
  - `ROAM_GRAPH_NAME`: Name of the Roam graph to access
- Support .env file for local development

## Testing Strategy
- Unit tests for individual components
- Integration tests for Roam API interactions
- Mock Roam API responses for testing
- Test edge cases: empty graphs, malformed blocks, permission issues

## Deployment
- For development: `mcp dev server.py`
- For Claude Desktop: `mcp install server.py`
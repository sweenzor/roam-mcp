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

**Pre-commit hooks**: This project uses pre-commit hooks to automatically run formatting, linting, and type checking before each commit.
- Install hooks (one-time setup): `uv run pre-commit install`
- Run hooks manually: `uv run pre-commit run --all-files`
- Skip hooks (not recommended): `git commit --no-verify`

The hooks automatically run:
1. **black** - Code formatting
2. **ruff** - Linting (with auto-fix)
3. **pyright** - Type checking

**Pre-commit checklist**: Before committing any changes:
1. Hooks run automatically (black, ruff, pyright)
2. Run the full test suite: `uv run pytest`
3. If `ROAM_API_TOKEN` and `ROAM_GRAPH_NAME` are available, also run e2e tests:
   - `uv run pytest tests/test_e2e.py -v`
   - `uv run pytest tests/test_e2e_search.py -v --no-cov`
4. Fix any test failures before committing

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
  - `embedding.py` - Embedding service using sentence-transformers
  - `vector_store.py` - Vector store using SQLite + sqlite-vec
- `/tests/` - Test directory
  - `test_server.py` - Basic unit tests for server tools
  - `test_server_unit.py` - Comprehensive unit tests with mocking
  - `test_roam_api_unit.py` - Unit tests for Roam API client
  - `test_embedding.py` - Unit tests for embedding service
  - `test_vector_store.py` - Unit tests for vector store
  - `test_e2e.py` - End-to-end tests (require API credentials)
  - `test_e2e_search.py` - E2E tests for semantic search enrichments (require API credentials)
  - `test_client.py` - MCP client integration test
  - `test_mcp_tools.py` - MCP server tools integration test
- `/reference/` - Reference implementations and documentation
  - `example-python-git-mcp-server/` - Example MCP server (pattern reference)
  - `example-roam-research-mcp-js/` - JavaScript Roam MCP (original inspiration)
  - `roam-python-sdk/` - Roam Python SDK (API client reference)
  - `readme-mcp-python-sdk.md` - MCP Python SDK documentation
  - `roam-research-general-info.md` - Roam Research background info
- `pyproject.toml` - Project metadata, dependencies, and build settings
- `.pre-commit-config.yaml` - Pre-commit hook configuration (black, ruff, pyright)
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

1. `hello_world`: Simple greeting tool for testing
   - Input: name (optional)
   - Output: Hello message

2. `get_page`: Retrieve page content in clean markdown format
   - Input: page title
   - Output: Markdown representation with properly indented blocks
   - Recursively handles blocks at any nesting depth

3. `create_block`: Add blocks to pages or under parent blocks
   - Input: content text, optional page uid or title
   - Output: Confirmation message with block UID

4. `daily_context`: Get daily notes with their backlinks for comprehensive context
   - Input: days (default: 10), max_references (default: 10)
   - Output: Markdown with daily note content + blocks that reference each daily note
   - Auto-detects daily note formats (June 13th, 2025 vs 06-13-2025 etc.)
   - Memory optimized with configurable limits

5. `sync_index`: Build or update the vector index for semantic search
   - Input: full (bool, default: False) - if True, rebuilds entire index
   - Output: Status message with sync statistics
   - Stores embeddings in `~/.roam-mcp/{graph_name}_vectors.db`
   - Uses all-MiniLM-L6-v2 model (384 dimensions)
   - Supports incremental updates (only new/modified blocks)

6. `semantic_search`: Search blocks using vector similarity
   - Input: query (string), limit (int, default: 10), include_context (bool, default: True)
   - Optional enrichments:
     - `include_children` (bool, default: False): Show nested child blocks
     - `children_limit` (int, default: 3): Max children to display
     - `include_backlink_count` (bool, default: False): Show count of blocks referencing each result
     - `include_siblings` (bool, default: False): Show adjacent sibling blocks for context
     - `sibling_count` (int, default: 1): Number of siblings before/after to show
   - Output: Formatted search results with similarity scores and enrichments
   - Always shows: modified timestamp, extracted tags (#tag), page links ([[page]])
   - Performs incremental sync before each search to capture recent changes
   - Applies recency boost (linear decay over 30 days, max 0.1 boost)
   - Returns parent chain context for each result
   - Minimum similarity threshold of 0.3

7. `get_block_context`: Get a block with its surrounding context
   - Input: uid (block UID)
   - Output: Block content with page title, parent chain, and nested children

8. `search_by_text`: Keyword/substring search (non-semantic)
   - Input: text (search string), page_title (optional), limit (default: 20)
   - Output: Matching blocks with UID, content, and page title
   - Case-sensitive substring matching using Datalog

9. `raw_query`: Execute arbitrary Datalog queries (power user tool)
   - Input: query (Datalog query string), args (optional list)
   - Output: Raw JSON results
   - Use with caution - allows direct database access

10. `get_backlinks`: Get all blocks that reference a page
    - Input: page_title, limit (default: 20)
    - Output: List of blocks with UID, content, and source page title

11. `quick_capture_enrich`: Enrich a quick note with page links
    - Input: note (raw text)
    - Output: JSON with enriched_note, matches_found, daily_note_title
    - Finds existing page names in the note and adds [[page links]]
    - Case-insensitive matching, preserves canonical page title case
    - Longer page names matched first to avoid partial matches
    - Skips pages already linked or tagged in the note
    - Minimum page name length: 3 characters

12. `quick_capture_commit`: Append a note to today's daily note
    - Input: note (the enriched or raw note text)
    - Output: Confirmation with daily note title and block UID
    - Appends to end of today's daily note page
    - Auto-detects daily note date format

Future tools to consider:
- `create_page`: Create new pages with optional content
- `import_markdown`: Import nested markdown content
- `add_todo`: Add todo items to daily pages
- `search_for_tag`: Search for blocks with specific tags
- `update_block`: Update block content
- `delete_block`: Delete blocks by UID
- `get_block_references`: Get all blocks that reference a specific block
- `export_graph`: Export entire graph or subsets in various formats

## Daily Notes Context Tool
The `daily_context` tool is a powerful feature for understanding your recent work patterns and connected topics:

### Features
- **Auto-detection**: Automatically detects your Roam's daily note format (June 13th, 2025, 06-13-2025, etc.)
- **Backlinks**: Finds all blocks that reference each daily note page (not content from daily notes)
- **Memory optimized**: Configurable limits to handle large datasets without memory issues
- **Flexible timeframes**: Fetch 1-30 days of context with configurable reference limits

### Usage Examples
- `daily_context`: Default - last 10 days, up to 10 references per day
- `daily_context(days=3)`: Last 3 days with default reference limit
- `daily_context(days=7, max_references=20)`: Last week with more references per day

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

## Quick Capture

The `quick_capture_enrich` and `quick_capture_commit` tools provide an interactive two-step workflow for capturing notes with automatic page linking.

### Workflow

1. **Enrich**: Call `quick_capture_enrich` with your raw note text
2. **Review**: Claude shows you the enriched note with page links added
3. **Approve/Edit**: You can approve or request changes
4. **Commit**: Call `quick_capture_commit` to append to your daily note

### Example

```
User: "Had a meeting with John about the AI project roadmap"

Claude calls quick_capture_enrich, which returns:
{
  "enriched_note": "Had a meeting with [[John]] about the [[AI project]] roadmap",
  "matches_found": ["John", "AI project"],
  "daily_note_title": "December 25th, 2025"
}

Claude: "Here's your enriched note with 2 page links added:
  'Had a meeting with [[John]] about the [[AI project]] roadmap'

  Add to December 25th, 2025?"

User: "Yes!"

Claude calls quick_capture_commit, returns:
  "Added to December 25th, 2025 (Block UID: abc123)"
```

### Matching Rules

- **Minimum length**: Pages must be 3+ characters to be matched
- **Case-insensitive**: Matches "john" to page "John"
- **Longer first**: "AI project" matches before "AI" alone
- **No duplicates**: If `[[John]]` already exists, "John" elsewhere won't be linked
- **Respects tags**: `#project` won't be double-linked as `[[project]]`
- **Word boundaries**: "projects" won't match page "project"

## Semantic Search Infrastructure

The server includes vector-based semantic search using sentence-transformers and sqlite-vec.

### Components

1. **EmbeddingService** (`embedding.py`)
   - Lazy-loads all-MiniLM-L6-v2 model (~90MB download on first use)
   - Generates 384-dimensional embeddings
   - Batched encoding for efficiency (default batch size: 64)
   - Formats blocks with page title context for richer embeddings

2. **VectorStore** (`vector_store.py`)
   - SQLite database with sqlite-vec extension for vector similarity search
   - Stores block metadata and embeddings separately
   - Per-graph databases at `~/.roam-mcp/{graph_name}_vectors.db`
   - Tracks sync state for incremental updates
   - KNN search using L2 distance converted to cosine similarity

### Database Schema
```sql
-- Block metadata
CREATE TABLE blocks (
    uid TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    page_uid TEXT,
    page_title TEXT,
    parent_uid TEXT,
    parent_chain TEXT,  -- JSON array
    edit_time INTEGER,
    embedded_at INTEGER
);

-- Sync state tracking
CREATE TABLE sync_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Vector embeddings (sqlite-vec virtual table)
CREATE VIRTUAL TABLE vec_embeddings USING vec0(
    uid TEXT PRIMARY KEY,
    embedding FLOAT[384]
);
```

### Bulk Fetch Methods (roam_api.py)
- `get_all_blocks_for_sync()`: Fetches all blocks with uid, content, edit_time, page info
- `get_blocks_modified_since(timestamp)`: Fetches blocks modified after a timestamp
- `get_block_parent_chain(block_uid)`: Gets parent block content strings for context

### Performance Characteristics
- Initial sync: ~90,000 blocks in ~6 minutes
- Index size: ~150MB for 90k blocks
- Search latency: <100ms
- Embedding model: ~90MB download on first use

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
- **Automatic retry with backoff**:
  - Network errors (ConnectionError, Timeout): 3 retries with exponential backoff (1s, 2s, 4s)
  - Rate limits (HTTP 429): 3 retries with longer backoff (10s, 20s, 40s)

## Performance Tuning

Key constants that can be adjusted for different graph sizes:

| Constant | File | Default | Description |
|----------|------|---------|-------------|
| `SYNC_BATCH_SIZE` | server.py | 64 | Blocks embedded per batch during sync |
| `SYNC_COMMIT_INTERVAL` | server.py | 500 | Blocks between database commits |
| `DEFAULT_BATCH_SIZE` | embedding.py | 64 | Batch size for embedding model |
| `SEARCH_MIN_SIMILARITY` | server.py | 0.3 | Minimum cosine similarity threshold |
| `RECENCY_BOOST_DAYS` | server.py | 30 | Days over which recency boost decays |
| `RECENCY_BOOST_MAX` | server.py | 0.1 | Maximum recency boost added to similarity |
| `MAX_RETRIES` | roam_api.py | 3 | Network error retry attempts |
| `RATE_LIMIT_RETRIES` | roam_api.py | 3 | Rate limit retry attempts |
| `REQUEST_TIMEOUT_SECONDS` | roam_api.py | 30 | HTTP request timeout |

**Tuning recommendations:**
- For larger graphs (>100k blocks): Increase `SYNC_BATCH_SIZE` to 128 if memory allows
- For slower connections: Increase `REQUEST_TIMEOUT_SECONDS` to 60
- For stricter search results: Increase `SEARCH_MIN_SIMILARITY` to 0.4-0.5
- For more recent content priority: Increase `RECENCY_BOOST_MAX` to 0.15-0.2

## Testing
- **Unit tests**: `test_server.py`, `test_server_unit.py` - run without API credentials
- **E2E tests**: `test_e2e.py` - require ROAM_API_TOKEN and ROAM_GRAPH_NAME env vars
- **E2E search tests**: `test_e2e_search.py` - test semantic search enrichments against real graph
- E2E tests auto-skip when credentials not available
- MCP Inspector for interactive testing: `uv run mcp dev`
- **Coverage targets**: Maintain 100% code coverage
- Use `pytest-cov` for coverage reporting
- Run e2e search tests with: `source .env && uv run pytest tests/test_e2e_search.py -v --no-cov`

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
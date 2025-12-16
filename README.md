# MCP Server for Roam Research

A Model Context Protocol (MCP) server that provides access to Roam Research functionality for LLMs.

## Features

- **Semantic Search** — Find relevant blocks by meaning, not just keywords. Built on [sentence-transformers](https://www.sbert.net/) and [sqlite-vec](https://github.com/asg017/sqlite-vec), the vector index captures the semantic relationships in your notes. Recent content gets a recency boost, and results include parent context so you understand where each block lives in your graph.

- **Daily Notes Context** — Understand your recent work at a glance. Fetches daily notes along with all blocks that reference them, automatically detecting your date format.

- **Full Graph Access** — Read pages as clean markdown, create blocks, execute Datalog queries, and traverse backlinks. Works with unlimited nesting depth.

- **Incremental Sync** — The semantic index updates automatically, only processing new or modified blocks. Initial indexing handles ~90k blocks in about 6 minutes; subsequent syncs take seconds.

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
| `hello_world` | Simple greeting for testing connectivity |
| `get_page` | Retrieve page content as markdown (unlimited nesting) |
| `create_block` | Create a new block in a Roam page |
| `daily_context` | Get daily notes with backlinks for context |
| `debug_daily_notes` | Debug daily note format detection |
| `sync_index` | Build/update the vector index for semantic search |
| `semantic_search` | Search blocks using vector similarity with recency boost |
| `get_block_context` | Get a block with parent chain and children |
| `search_by_text` | Keyword/substring search (non-semantic) |
| `raw_query` | Execute arbitrary Datalog queries (power user tool) |
| `get_backlinks` | Get all blocks that reference a page |

### Key Features

- **Semantic Search**: Vector-based search across all blocks using sentence-transformers
- **Keyword Search**: Fast text substring search with `search_by_text`
- **Backlinks**: Find all blocks referencing any page with `get_backlinks`
- **Raw Queries**: Execute custom Datalog queries with `raw_query`
- **Daily Note Context**: `daily_context` fetches recent daily notes + all blocks that reference them
- **Auto-detection**: Automatically detects daily note formats (e.g., "June 13th, 2025", "06-13-2025")
- **Recursive Processing**: Handles unlimited block nesting depth
- **Error Handling**: Graceful handling of missing pages and API errors

## Semantic Search

The server includes a vector-based semantic search capability powered by [sentence-transformers](https://www.sbert.net/) and [sqlite-vec](https://github.com/asg017/sqlite-vec).

### How It Works

1. **Indexing**: `sync_index` fetches all blocks from your Roam graph and generates embeddings using the `all-MiniLM-L6-v2` model (384 dimensions)
2. **Storage**: Embeddings are stored locally in `~/.roam-mcp/{graph_name}_vectors.db`
3. **Search**: Query embeddings are compared against stored embeddings using cosine similarity

### Usage

```bash
# First, build the index (takes ~6 minutes for 90k blocks)
# Call sync_index via MCP or:
uv run python -c "
from mcp_server_roam.server import sync_index
print(sync_index(full=True))
"

# Incremental updates (only new/modified blocks)
sync_index(full=False)

# Search your Roam graph semantically
uv run python -c "
from mcp_server_roam.server import semantic_search
print(semantic_search('project management tools', limit=5))
"
```

### Search Features

- **Incremental Sync**: Automatically syncs new/modified blocks before each search
- **Recency Boost**: Recent content (last 30 days) ranks higher with linear decay
- **Parent Context**: Results include parent block chain for understanding hierarchy
- **Similarity Threshold**: Filters out low-relevance results (default: 0.3)

### Performance

- Initial sync: ~90,000 blocks indexed in ~6 minutes
- Index size: ~150MB for 90k blocks
- Search latency: <100ms
- Embedding model downloads ~90MB on first use

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

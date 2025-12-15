# Roam Research MCP Server with Semantic Search

## Overview

Build a Python MCP server that connects to a Roam Research graph via the official API and provides both direct graph access and semantic (vector) search capabilities. The server will be used with Claude Desktop.

## Goals

1. **Real-time graph access** — Query pages, blocks, backlinks, and linked references directly from Roam
2. **Semantic search** — Find relevant content by meaning, not just keyword matching
3. **Incremental sync** — Keep the vector index updated without re-embedding the entire graph
4. **Graph-aware context** — When returning search results, include surrounding context (parent blocks, page title, backlinks)

## User Context

- Graph size: ~10k pages, 19MB of text
- Heavy use of daily note pages
- High technical comfort level
- OK with sending data to embedding APIs

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      MCP Server (Python)                    │
│                                                             │
│  ┌─────────────────┐       ┌─────────────────────────────┐ │
│  │  Roam API       │       │   Semantic Search Module    │ │
│  │  Client         │       │                             │ │
│  │                 │       │  ┌─────────────────────┐    │ │
│  │  • query()      │       │  │  Embedding Service  │    │ │
│  │  • pull()       │       │  │  (OpenAI or local)  │    │ │
│  │  • create/      │       │  └─────────────────────┘    │ │
│  │    update/      │       │             │               │ │
│  │    delete       │       │             ▼               │ │
│  └─────────────────┘       │  ┌─────────────────────┐    │ │
│           │                │  │  SQLite + sqlite-   │    │ │
│           │                │  │  vss (vector store) │    │ │
│           │                │  └─────────────────────┘    │ │
│           │                └─────────────────────────────┘ │
│           │                              │                  │
│           └──────────────┬───────────────┘                  │
│                          ▼                                  │
│              ┌─────────────────────┐                        │
│              │    MCP Tools        │                        │
│              │    (exposed to      │                        │
│              │     Claude)         │                        │
│              └─────────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Roam API Details

### Authentication
- Base URL: `https://api.roamresearch.com`
- Auth header: `Authorization: Bearer {API_TOKEN}`
- Graph specified in URL path: `/api/graph/{GRAPH_NAME}/q`

### Key Endpoints

**Query (Datalog)**
```
POST /api/graph/{graph}/q
Content-Type: application/json

{
  "query": "[:find ?uid ?string :where [?b :block/uid ?uid] [?b :block/string ?string]]",
  "args": []
}
```

**Pull (fetch entity by UID)**
```
POST /api/graph/{graph}/pull
Content-Type: application/json

{
  "eid": "[:block/uid \"abc123\"]",
  "selector": "[*]"
}
```

**Write Operations**
- `POST /api/graph/{graph}/write` with actions like `create-block`, `update-block`, `delete-block`, `create-page`

### Useful Datalog Queries

**Get all pages:**
```clojure
[:find ?uid ?title
 :where
 [?p :node/title ?title]
 [?p :block/uid ?uid]]
```

**Get blocks modified since timestamp:**
```clojure
[:find ?uid ?string ?time
 :where
 [?b :block/uid ?uid]
 [?b :block/string ?string]
 [?b :edit/time ?time]
 [(> ?time {timestamp_ms})]]
```

**Get page content with children:**
```clojure
[:find (pull ?p [:node/title :block/uid {:block/children ...}])
 :where
 [?p :node/title "{page_title}"]]
```

**Get backlinks to a page:**
```clojure
[:find ?ref-uid ?ref-string
 :where
 [?page :node/title "{page_title}"]
 [?ref :block/refs ?page]
 [?ref :block/string ?ref-string]
 [?ref :block/uid ?ref-uid]]
```

**Get linked references (pages this page links to):**
```clojure
[:find ?linked-title
 :where
 [?page :node/title "{page_title}"]
 [?block :block/page ?page]
 [?block :block/refs ?linked]
 [?linked :node/title ?linked-title]]
```

---

## MCP Tools to Expose

### 1. `semantic_search`
Search the graph by meaning/concept.

**Parameters:**
- `query` (string): Natural language search query
- `limit` (int, default 10): Max results to return
- `include_context` (bool, default true): Include parent hierarchy and page title

**Returns:** List of relevant blocks with:
- Block UID
- Block content
- Page title
- Parent block chain (for hierarchy context)
- Similarity score

**Implementation:**
1. Check if any blocks modified since last sync → embed them first
2. Embed the query
3. Vector search in SQLite-vss
4. For each result, fetch context from Roam API
5. Return enriched results

### 2. `get_page`
Fetch a page by title with full content.

**Parameters:**
- `title` (string): Page title (case-sensitive)
- `include_linked_refs` (bool, default false): Include blocks that link to this page

**Returns:**
- Page UID
- Page title
- Nested block content (full tree)
- Optionally: linked references

### 3. `get_block_context`
Get a block with its surrounding context.

**Parameters:**
- `uid` (string): Block UID

**Returns:**
- Block content
- Parent chain (up to page)
- Children (1-2 levels)
- Page title
- Sibling blocks (optional)

### 4. `get_backlinks`
Get all blocks that reference a page.

**Parameters:**
- `page_title` (string): Title of the page

**Returns:** List of blocks referencing this page, with their page titles and UIDs

### 5. `get_daily_note`
Get today's daily note (or a specific date).

**Parameters:**
- `date` (string, optional): Date in "MM-DD-YYYY" format. Defaults to today.

**Returns:** Full content of the daily note page

### 6. `search_by_text`
Keyword/substring search (non-semantic).

**Parameters:**
- `text` (string): Text to search for
- `page_title` (string, optional): Limit search to a specific page

**Returns:** Matching blocks with context

### 7. `raw_query`
Execute arbitrary Datalog query (for power users).

**Parameters:**
- `query` (string): Datalog query
- `args` (list, optional): Query arguments

**Returns:** Raw query results

---

## Vector Index Design

### Storage: SQLite + sqlite-vss

Use a local SQLite database with the `sqlite-vss` extension for vector similarity search. This keeps everything local and avoids external vector DB dependencies.

### Schema

```sql
CREATE TABLE blocks (
    uid TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    page_uid TEXT,
    page_title TEXT,
    parent_uid TEXT,
    parent_chain TEXT,  -- JSON array of parent block strings for context
    edit_time INTEGER,  -- milliseconds since epoch
    embedded_at INTEGER -- when we last embedded this block
);

CREATE TABLE embeddings (
    uid TEXT PRIMARY KEY,
    embedding BLOB,  -- vector as bytes
    FOREIGN KEY (uid) REFERENCES blocks(uid)
);

CREATE TABLE sync_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- Store last_sync_timestamp here

CREATE VIRTUAL TABLE vss_embeddings USING vss0(
    embedding(1536)  -- OpenAI ada-002 dimension, adjust if using different model
);
```

### Chunking Strategy

Each block becomes one vector, but the text we embed includes context:
```
Page: {page_title}
Path: {parent1} > {parent2} > {parent3}
Content: {block_content}
```

This helps the embedding capture hierarchical context.

### Embedding Model Options

**Recommended: OpenAI text-embedding-3-small**
- 1536 dimensions
- Fast, cheap ($0.02/1M tokens)
- High quality

**Alternative: Local with sentence-transformers**
- Model: `all-MiniLM-L6-v2` (384 dimensions)
- Free, private
- Slightly lower quality

---

## Sync Strategy

### Initial Full Sync
1. Query all blocks from Roam
2. Build parent chains for each block
3. Embed all blocks in batches
4. Store in SQLite

For 19MB / 10k pages, estimate:
- ~50-100k blocks
- ~$1-2 in embedding costs
- 10-20 minutes

### Incremental Sync (Query-Time)

Before each semantic search:

1. Get `last_sync_timestamp` from `sync_state` table
2. Query Roam for blocks modified since then:
   ```clojure
   [:find ?uid ?string ?time
    :where
    [?b :block/uid ?uid]
    [?b :block/string ?string]
    [?b :edit/time ?time]
    [(> ?time {last_sync_timestamp})]]
   ```
3. For modified blocks:
   - Fetch full context (parent chain, page title)
   - Re-embed
   - Update SQLite
4. Update `last_sync_timestamp`
5. Proceed with search

This adds minimal latency (typically <1 second for a day's edits).

### Handling Deletions

Roam doesn't easily expose deleted blocks. Options:
- Periodic full reconciliation (e.g., weekly)
- Accept some stale entries (they'll have low relevance anyway)
- Track known UIDs and periodically verify they still exist

---

## Tech Stack

- **Python 3.11+**
- **MCP SDK**: `mcp` package for Python
- **HTTP client**: `httpx` for async Roam API calls
- **Vector store**: `sqlite-vss` (or `sqlite-vec` as alternative)
- **Embeddings**: `openai` package (or `sentence-transformers` for local)
- **Config**: Environment variables or `.env` file

### Dependencies

```
mcp
httpx
openai
sqlite-vss  # or sqlite-vec
python-dotenv
```

---

## Configuration

Environment variables:

```bash
ROAM_API_TOKEN=your-api-token
ROAM_GRAPH_NAME=your-graph-name
OPENAI_API_KEY=your-openai-key  # if using OpenAI embeddings
EMBEDDING_MODEL=text-embedding-3-small  # or "local" for sentence-transformers
VECTOR_DB_PATH=~/.roam-mcp/vectors.db
```

---

## Implementation Phases

### Phase 1: Core Roam API Client
- Implement authenticated requests to Roam API
- Build query helpers for common Datalog patterns
- Test fetching pages, blocks, backlinks

### Phase 2: MCP Server Shell
- Set up MCP server with Python SDK
- Implement non-semantic tools first:
  - `get_page`
  - `get_block_context`
  - `get_backlinks`
  - `get_daily_note`
  - `search_by_text`
  - `raw_query`
- Test with Claude Desktop

### Phase 3: Vector Index
- Set up SQLite with sqlite-vss
- Implement embedding service (OpenAI or local)
- Build initial sync: fetch all blocks, embed, store
- Implement incremental sync logic

### Phase 4: Semantic Search
- Implement `semantic_search` tool
- Add query-time incremental sync
- Enrich results with context from Roam API
- Test and tune retrieval quality

### Phase 5: Polish
- Error handling and retries
- Logging
- Performance optimization (batch embedding, caching)
- Documentation

---

## Claude Desktop Integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "roam": {
      "command": "python",
      "args": ["-m", "roam_mcp_server"],
      "env": {
        "ROAM_API_TOKEN": "your-token",
        "ROAM_GRAPH_NAME": "your-graph",
        "OPENAI_API_KEY": "your-key"
      }
    }
  }
}
```

Or if using uv/uvx:
```json
{
  "mcpServers": {
    "roam": {
      "command": "uvx",
      "args": ["roam-mcp-server"],
      "env": { ... }
    }
  }
}
```

---

## Example Usage (from Claude's perspective)

**User:** "What have I written about raising money for startups?"

**Claude:**
1. Calls `semantic_search(query="raising money for startups venture capital fundraising")`
2. Gets back relevant blocks with context
3. If needed, calls `get_page` or `get_backlinks` to explore connections
4. Synthesizes answer from the retrieved content

**User:** "Show me my notes from the meeting with John last Tuesday"

**Claude:**
1. Calculates date for "last Tuesday"
2. Calls `get_daily_note(date="12-10-2024")` 
3. Also calls `semantic_search(query="meeting John")` to find related content
4. Returns relevant sections

---

## Open Questions / Decisions for Implementation

1. **sqlite-vss vs sqlite-vec**: sqlite-vec is newer and may have better performance. Research which is better supported.

2. **Embedding batch size**: What's the optimal batch size for embedding calls? (Probably 100-500 texts per request)

3. **Context window for embedding**: How much parent context to include? Too much dilutes the block's meaning; too little loses context.

4. **Result ranking**: Pure vector similarity, or hybrid with recency/importance weighting?

5. **Block size threshold**: Should we skip very short blocks (e.g., single words)? Or embed everything?

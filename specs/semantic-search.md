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
- Prefer local embeddings for privacy

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
│  │  • pull()       │       │  │  (sentence-         │    │ │
│  │  • create/      │       │  │   transformers)     │    │ │
│  │    update/      │       │  └─────────────────────┘    │ │
│  │    delete       │       │             │               │ │
│  └─────────────────┘       │             ▼               │ │
│           │                │  ┌─────────────────────┐    │ │
│           │                │  │  SQLite + sqlite-   │    │ │
│           │                │  │  vec (vector store) │    │ │
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

**Note:** These tools replace the existing `roam_*` prefixed tools. The new naming convention drops the prefix for cleaner tool names.

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
3. Vector search in sqlite-vec
4. Apply recency boost to ranking
5. Filter results below similarity threshold
6. For each result, fetch context from Roam API
7. Return enriched results

### 2. `get_page`
Fetch a page by title with full content. (Replaces `roam_get_page_markdown`)

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

### 8. `create_block`
Add blocks to pages or under parent blocks. (Replaces `roam_create_block`)

**Parameters:**
- `content` (string): Block content
- `page_title` (string, optional): Page to add block to
- `parent_uid` (string, optional): Parent block UID

**Returns:** Created block UID and confirmation

### 9. `daily_context`
Get daily notes with their backlinks for comprehensive context. (Replaces `roam_context`)

**Parameters:**
- `days` (int, default 10): Number of days to fetch
- `max_references` (int, default 10): Max references per day

**Returns:** Markdown with daily note content + blocks that reference each daily note

### 10. `sync_index`
Build or rebuild the vector index for semantic search.

**Parameters:**
- `full` (bool, default false): Force full resync even if index exists

**Returns:** Final status (blocks synced, time taken)

**Progress reporting:** Uses MCP Context for real-time updates:
```python
ctx.info(f"Fetching blocks from Roam...")
await ctx.report_progress(i, total_blocks)
```

**Behavior:**
- If no index exists: performs full sync of all blocks
- If index exists and `full=false`: performs incremental sync only
- If index exists and `full=true`: drops and rebuilds entire index

This allows Claude to detect when semantic_search fails due to missing index and suggest running sync, with user approval via normal MCP tool flow.

---

## Vector Index Design

### Storage: SQLite + sqlite-vec

Use a local SQLite database with the `sqlite-vec` extension for vector similarity search. sqlite-vec is the actively maintained successor to sqlite-vss, with better performance and ongoing development.

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

-- sqlite-vec virtual table for vector search
CREATE VIRTUAL TABLE vec_embeddings USING vec0(
    uid TEXT PRIMARY KEY,
    embedding FLOAT[384]  -- all-MiniLM-L6-v2 dimension
);
```

### Chunking Strategy

Each block becomes one vector. The text we embed includes full hierarchical context:
```
Page: {page_title}
Path: {parent1} > {parent2} > ... > {parentN}
Content: {block_content}
```

This helps the embedding capture hierarchical context. The full parent path is included.

**Design decision:** Embed all blocks regardless of length. This is the simplest approach. If performance or quality suffers, revisit with options like:
- Skip blocks under N characters
- Concatenate short parent + children into one embedding

### Embedding Model

**Local with sentence-transformers (chosen for privacy)**
- Model: `all-MiniLM-L6-v2`
- 384 dimensions
- Free, completely private
- Good quality for semantic similarity

---

## Sync Strategy

### Initial Full Sync

When `semantic_search` is called with no vector index, it returns a message indicating sync is needed. Claude can then suggest calling `sync_index`, and the user approves via normal MCP tool flow.

Initial sync steps:
1. Query all blocks from Roam
2. Build parent chains for each block
3. Embed all blocks in batches
4. Store in SQLite

For 19MB / 10k pages, estimate:
- ~50-100k blocks
- 10-20 minutes (local embedding)

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

## Search Ranking

Results are ranked using a hybrid approach:

1. **Vector similarity** (primary): Cosine similarity from sqlite-vec
2. **Recency boost**: Recently edited blocks get a boost to their score
3. **Similarity threshold**: Results below a minimum similarity score (e.g., 0.3) are filtered out

**Future improvements to consider:**
- Reference count boost (well-linked blocks rank higher)
- Page type filtering (exclude daily notes from general search)

---

## Tech Stack

- **Python 3.11+**
- **MCP SDK**: `mcp` package for Python
- **HTTP client**: `httpx` for async Roam API calls
- **Vector store**: `sqlite-vec`
- **Embeddings**: `sentence-transformers` (local)
- **Config**: Environment variables or `.env` file

### Dependencies

```
mcp
httpx
sqlite-vec
sentence-transformers
python-dotenv
```

---

## Configuration

Environment variables:

```bash
ROAM_API_TOKEN=your-api-token
ROAM_GRAPH_NAME=your-graph-name
VECTOR_DB_PATH=~/.roam-mcp/vectors.db
```

---

## Implementation Phases

### Phase 1: Core Roam API Client ✓
- Implement authenticated requests to Roam API
- Build query helpers for common Datalog patterns
- Test fetching pages, blocks, backlinks

*Status: Already implemented in `roam_api.py`*

### Phase 2: MCP Server with Basic Tools ✓
- Set up MCP server with Python SDK
- Implement basic tools (`get_page`, `create_block`, `daily_context`)

*Status: Mostly complete. Existing tools work.*

### Phase 2.5: Additional Non-Semantic Tools
- Add `get_block_context` tool
- Add `search_by_text` tool (keyword search via Datalog)
- Add `raw_query` tool
- Add `get_backlinks` tool
- Rename existing tools to drop `roam_` prefix
- Test with Claude Desktop

### Phase 3: Vector Index
- Set up SQLite with sqlite-vec
- Implement embedding service with sentence-transformers
- Implement `sync_index` tool for full/incremental sync
- Build sync logic: fetch all blocks, embed, store

### Phase 4: Semantic Search
- Implement `semantic_search` tool
- Add query-time incremental sync
- Implement recency boost ranking
- Add similarity threshold filtering
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
      "command": "uv",
      "args": ["--directory", "/path/to/roam-mcp", "run", "python", "-m", "mcp_server_roam"],
      "env": {
        "ROAM_API_TOKEN": "your-token",
        "ROAM_GRAPH_NAME": "your-graph"
      }
    }
  }
}
```

---

## Example Usage (from Claude's perspective)

**User:** "What have I written about raising money for startups?"

**Claude:**
1. Calls `semantic_search(query="raising money for startups venture capital fundraising")`
2. Gets back relevant blocks with context, ranked by similarity + recency
3. If needed, calls `get_page` or `get_backlinks` to explore connections
4. Synthesizes answer from the retrieved content

**User:** "Show me my notes from the meeting with John last Tuesday"

**Claude:**
1. Calculates date for "last Tuesday"
2. Calls `get_daily_note(date="12-10-2024")`
3. Also calls `semantic_search(query="meeting John")` to find related content
4. Returns relevant sections

---

## Design Decisions Log

Decisions made during planning:

| Question | Decision | Notes |
|----------|----------|-------|
| sqlite-vss vs sqlite-vec | sqlite-vec | Actively maintained, better performance |
| Embedding model | Local (sentence-transformers) | Privacy, no API costs |
| Block size threshold | Embed everything | Revisit if quality/perf issues |
| Parent context depth | Full path | Revisit if embedding quality suffers |
| Sync strategy | Query-time incremental | Acceptable latency |
| Initial sync UX | `sync_index` tool | Claude suggests, user approves via MCP flow |
| Result ranking | Similarity + recency boost | Add more signals later if needed |
| Similarity threshold | Yes, filter low scores | Prevent irrelevant results |
| Tool naming | Drop `roam_` prefix | Cleaner, replaces existing tools |

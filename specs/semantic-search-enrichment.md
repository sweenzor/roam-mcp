# Semantic Search Enrichment Plan

## Overview

Enrich semantic search results with additional context to help users better understand and navigate search results within Roam's graph structure.

## Current State

Each search result currently includes:
- **Similarity score** (cosine similarity with recency boost)
- **Page title** (containing page)
- **Parent chain** (breadcrumb path as strings)
- **Content** (block text, truncated to 500 chars)
- **UID** (block identifier)

## Implementation Phases

### Phase 1: Children Preview (High Value, Medium Cost)

**Why:** Roam blocks often have important context in their children. A matching block may be a header with details below.

**Implementation:**
1. Add `include_children: bool = False` parameter to `semantic_search`
2. Add `children_limit: int = 3` parameter to control preview size
3. Create new method `get_block_children_preview(uid, limit)` in `roam_api.py`
4. After fetching results, batch-fetch children for all results
5. Add children preview section to output format

**Output format change:**
```markdown
## 1. [0.847] Project Planning
**Path:** Q1 Goals > Engineering
Implement the new search feature with vector embeddings
*UID: abc123def*

**Children:**
  - Use sentence-transformers for embeddings
  - Store in SQLite with sqlite-vec
  - Target <100ms search latency
```

**API calls:** 1 query per search (batched)

**Files to modify:**
- `server.py`: Add parameters, fetch children, update output format
- `roam_api.py`: Add `get_block_children_preview()` method

---

### Phase 2: Tag and Page Reference Extraction (High Value, Low Cost)

**Why:** Tags and page references are core to Roam's linking structure. Showing them helps users understand connections.

**Implementation:**
1. Add helper function `extract_references(content: str) -> dict` that returns:
   - `tags`: List of #hashtags
   - `page_refs`: List of [[Page Name]] references
2. Parse content using regex patterns
3. Display extracted references in output

**Output format change:**
```markdown
## 1. [0.847] Project Planning
**Path:** Q1 Goals > Engineering
**Tags:** #project, #engineering
**Links:** [[Search Feature]], [[Vector DB]]
Implement the new search feature with vector embeddings for [[Search Feature]]
*UID: abc123def*
```

**API calls:** 0 (parsing existing content)

**Files to modify:**
- `server.py`: Add extraction function, update output format

---

### Phase 3: Edit Timestamp Display (Medium Value, Zero Cost)

**Why:** Knowing when content was last modified helps assess relevance and freshness.

**Implementation:**
1. Format `edit_time` (already fetched) as human-readable date
2. Add to output format

**Output format change:**
```markdown
## 1. [0.847] Project Planning
**Path:** Q1 Goals > Engineering
**Modified:** Dec 15, 2025
...
```

**API calls:** 0 (data already available)

**Files to modify:**
- `server.py`: Format timestamp, update output

---

### Phase 4: Backlink Count (Medium Value, Medium Cost)

**Why:** Blocks with many backlinks are often more important/central concepts.

**Implementation:**
1. Add `include_backlink_count: bool = False` parameter
2. Create `get_block_reference_count(uid)` in `roam_api.py`
3. Batch query to count references to each result block
4. Display count in output

**Output format change:**
```markdown
## 1. [0.847] Project Planning
**Path:** Q1 Goals > Engineering
**Modified:** Dec 15, 2025 | **Referenced by:** 12 blocks
...
```

**API calls:** 1 query per search (batched)

**Files to modify:**
- `server.py`: Add parameter, fetch counts, update output
- `roam_api.py`: Add `get_block_reference_counts()` method

---

### Phase 5: Sibling Context (Medium Value, High Cost)

**Why:** Surrounding blocks at the same level often provide important context.

**Implementation:**
1. Add `include_siblings: bool = False` parameter
2. Add `sibling_count: int = 1` parameter (blocks before/after)
3. Create `get_block_siblings(uid, count)` in `roam_api.py`
4. Fetch parent, then get ordered children to find siblings
5. Display siblings with visual indicator

**Output format change:**
```markdown
## 1. [0.847] Project Planning
**Path:** Q1 Goals > Engineering

**Context:**
  ↑ Previous task completed successfully
  → **Implement the new search feature with vector embeddings**
  ↓ Next: Deploy to production

*UID: abc123def*
```

**API calls:** 1-2 queries per result (potentially expensive)

**Files to modify:**
- `server.py`: Add parameters, fetch siblings, update output
- `roam_api.py`: Add `get_block_siblings()` method

---

## Future Enhancements (Track for Later)

### Full Backlinks Preview
- Show actual content of blocks that reference each result
- High API cost but very valuable for understanding connections
- Could be on-demand via `get_block_context` tool

### Related Semantic Blocks
- Group results that are semantically similar to each other
- Cluster results by topic
- Show "also relevant" blocks from same page

### Block Properties
- Extract and display Roam properties (key:: value)
- Useful for structured data in Roam

### Creation Context
- Show who created the block (if available)
- Show creation timestamp vs edit timestamp

---

## Recommended Implementation Order

1. **Phase 2: Tags/References** - Zero API cost, high value, quick win
2. **Phase 3: Edit Timestamp** - Zero API cost, easy implementation
3. **Phase 1: Children Preview** - High value, moderate complexity
4. **Phase 4: Backlink Count** - Moderate value, shows graph importance
5. **Phase 5: Siblings** - Complex, save for last

---

## Updated SemanticSearch Input Schema

```python
class SemanticSearch(BaseModel):
    """Input schema for semantic_search tool."""

    query: str
    limit: int = 10
    include_context: bool = True      # existing: parent chain
    include_children: bool = False    # Phase 1: children preview
    children_limit: int = 3           # Phase 1: max children to show
    include_backlink_count: bool = False  # Phase 4: reference counts
    include_siblings: bool = False    # Phase 5: sibling blocks
    sibling_count: int = 1            # Phase 5: blocks before/after
```

---

## Testing Strategy

For each phase:
1. Add unit tests with mocked API responses
2. Update existing semantic search tests
3. Add integration test with real graph (E2E)
4. Test output formatting
5. Verify no performance regression

---

## Success Metrics

- Search results provide enough context to understand relevance
- Users can navigate to related content without additional queries
- Performance remains acceptable (<500ms for typical searches)
- API call count stays within rate limits

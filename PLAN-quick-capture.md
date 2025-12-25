# Quick Capture Feature Plan

## Overview

An interactive two-step workflow for capturing notes with automatic page linking:

1. **Enrich**: User submits a note → Claude finds matching page names → shows enriched draft
2. **Commit**: User approves (or edits) → Claude appends to today's daily note

## User Flow

```
User: "quick capture: Had a meeting with John about the AI project roadmap"

Claude: Here's your enriched note:
  "Had a meeting with [[John]] about the [[AI project]] roadmap"

  Found 2 page matches: John, AI project

  Would you like me to add this to today's daily note?

User: Yes, looks good!

Claude: Added to December 25th, 2025 ✓
```

## Implementation

### 1. New Roam API Method: `get_all_page_titles()`

**File**: `src/mcp_server_roam/roam_api.py`

```python
def get_all_page_titles(self) -> list[str]:
    """Get all page titles in the graph."""
    query = "[:find ?title :where [?e :node/title ?title]]"
    results = self.run_query(query)
    return [r[0] for r in results if r[0]]
```

### 2. New Tool: `quick_capture_enrich`

**Purpose**: Enrich a note with page links based on existing pages in the graph.

**Input Schema**:
```python
class QuickCaptureEnrich(BaseModel):
    """Input schema for quick_capture_enrich tool."""
    note: str  # The raw note text to enrich
```

**Output**: JSON with:
- `enriched_note`: The note with [[page links]] added
- `matches_found`: List of page names that were linked
- `daily_note_title`: Today's daily note page title

**Matching Algorithm**:
1. Fetch all page titles from graph
2. Skip pages that are already linked in the note
3. Sort pages by length descending (match "AI Strategy" before "AI")
4. Case-insensitive matching
5. Match whole words only (avoid linking "project" inside "projects")
6. Replace matches with `[[Original Case]]` format

### 3. New Tool: `quick_capture_commit`

**Purpose**: Append an enriched note to today's daily note page.

**Input Schema**:
```python
class QuickCaptureCommit(BaseModel):
    """Input schema for quick_capture_commit tool."""
    note: str  # The final note text (enriched or edited)
```

**Behavior**:
1. Detect daily note format using existing `find_daily_note_format()`
2. Get today's date formatted as page title
3. Append block to daily note page (using `order: "last"`)
4. Return confirmation with daily note title and block UID

### 4. Modify `create_block` (optional enhancement)

Add optional `order` parameter to support appending:
```python
class CreateBlock(BaseModel):
    content: str
    page_uid: str | None = None
    title: str | None = None
    order: int | str = 0  # 0 for prepend, "last" for append
```

Or create a dedicated internal helper for appending.

## File Changes

| File | Changes |
|------|---------|
| `src/mcp_server_roam/roam_api.py` | Add `get_all_page_titles()` method |
| `src/mcp_server_roam/server.py` | Add `QuickCaptureEnrich` and `QuickCaptureCommit` models |
| `src/mcp_server_roam/server.py` | Add `quick_capture_enrich()` function |
| `src/mcp_server_roam/server.py` | Add `quick_capture_commit()` function |
| `src/mcp_server_roam/server.py` | Register both tools in `list_tools()` |
| `src/mcp_server_roam/server.py` | Add cases in `call_tool()` handler |
| `tests/test_server_unit.py` | Unit tests for enrichment logic |
| `tests/test_e2e.py` | E2E test for full workflow |

## Matching Edge Cases

1. **Already linked pages**: Skip text already inside `[[...]]`
2. **Overlapping matches**: Longer matches take priority
3. **Case preservation**: Match case-insensitively, but preserve original case in link
4. **Word boundaries**: Only match complete words/phrases
5. **Special characters**: Handle page names with special regex chars
6. **Nested brackets**: Handle `[[page [[nested]]]]` gracefully

## Testing Strategy

### Unit Tests
- Enrichment with no matches → returns original note
- Enrichment with single match → adds link correctly
- Enrichment with multiple matches → links all
- Overlapping matches → longer wins
- Already linked text → not double-linked
- Case insensitive matching with case preservation
- Special characters in page names

### E2E Tests
- Full workflow: enrich → commit → verify block exists
- Daily note format detection works
- Block appears at end of daily note

## Open Questions

1. **Minimum page name length?** Should we skip very short page names (e.g., "AI", "Go") to avoid false positives?
   - Recommendation: Allow configuration, default to 2+ characters

2. **Maximum matches?** Should we limit how many links are added to avoid over-linking?
   - Recommendation: No limit, but show count to user

3. **Tag matching?** Should we also match `#tags` in addition to `[[pages]]`?
   - Recommendation: Focus on pages first, tags can be added later

4. **Nested content?** Should the note support multiple lines / bullet points?
   - Recommendation: Start with single block, can extend later

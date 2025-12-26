# Multi-line Quick Capture Plan

## Overview

Extend quick capture to support multi-line notes with indentation, creating nested block structures in Roam.

## Input Format

Support markdown-style bullets with 2-space indentation:

```
Meeting with John about AI project
- Discussed roadmap
  - Q1 goals
  - Q2 timeline
- Action items
  - Send proposal
  - Schedule follow-up
```

Or plain text with indentation:

```
Meeting notes
  First topic
    Sub-point
  Second topic
```

## Parsing Strategy

1. **Split into lines**, preserving empty lines as block separators
2. **Detect indentation level** for each line:
   - Count leading whitespace (2 spaces = 1 level, 4 spaces = 2 levels)
   - Strip optional `- ` or `* ` bullet prefix
3. **Build tree structure** tracking parent-child relationships

## Data Structure

```python
@dataclass
class CaptureBlock:
    content: str           # The text content (to be enriched)
    level: int             # Indentation level (0 = root)
    children: list[CaptureBlock]
    temp_uid: int          # Negative number for batch action reference
```

## Implementation

### 1. New Pydantic Model

```python
class QuickCaptureMultiline(BaseModel):
    note: str  # Multi-line note with indentation
```

### 2. Parse Function

```python
def parse_multiline_note(note: str) -> list[CaptureBlock]:
    """Parse multi-line note into tree structure."""
    lines = note.split('\n')
    root_blocks = []
    stack = [(root_blocks, -1)]  # (children list, level)

    for line in lines:
        if not line.strip():
            continue

        # Count indentation
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        level = indent // 2

        # Remove bullet if present
        if stripped.startswith(('- ', '* ')):
            content = stripped[2:]
        else:
            content = stripped

        block = CaptureBlock(content=content, level=level, children=[])

        # Find correct parent
        while stack and stack[-1][1] >= level:
            stack.pop()

        parent_list = stack[-1][0]
        parent_list.append(block)
        stack.append((block.children, level))

    return root_blocks
```

### 3. Batch Action Builder

```python
def build_batch_actions(
    blocks: list[CaptureBlock],
    page_uid: str,
) -> list[dict]:
    """Convert block tree to Roam batch actions."""
    actions = []
    temp_uid_counter = -1

    def add_block(block: CaptureBlock, parent_uid: str | int) -> int:
        nonlocal temp_uid_counter
        my_uid = temp_uid_counter
        temp_uid_counter -= 1

        actions.append({
            "action": "create-block",
            "location": {"parent-uid": parent_uid, "order": "last"},
            "block": {"string": block.content, "uid": my_uid},
        })

        for child in block.children:
            add_block(child, my_uid)

        return my_uid

    for block in blocks:
        add_block(block, page_uid)

    return actions
```

### 4. New Roam API Method

```python
def batch_write(self, actions: list[dict]) -> dict:
    """Execute multiple write actions in a single request."""
    path = f"/api/graph/{self.graph_name}/write"
    body = {
        "action": "batch-actions",
        "actions": actions,
    }
    resp = self.call(path, body)
    return resp.json()
```

### 5. Updated Enrich Function

```python
def enrich_multiline_note(note: str, page_titles: list[str]) -> dict:
    """Enrich each line of a multi-line note."""
    blocks = parse_multiline_note(note)

    def enrich_block(block: CaptureBlock) -> None:
        result = enrich_note_with_links(block.content, page_titles)
        block.content = result["enriched_note"]
        for child in block.children:
            enrich_block(child)

    for block in blocks:
        enrich_block(block)

    return blocks
```

### 6. New Tools

**`quick_capture_multiline_enrich`**
- Input: `note` (multi-line string)
- Output: JSON with:
  - `enriched_note`: Formatted preview of nested structure
  - `matches_found`: All page matches across all lines
  - `block_count`: Number of blocks to create
  - `daily_note_title`: Target page

**`quick_capture_multiline_commit`**
- Input: `note` (the multi-line text, enriched or not)
- Uses `batch_write` to create all blocks atomically
- Returns: Confirmation with block count

## Example Flow

**Input:**
```
Call with John
- Discussed AI project
  - Timeline looks good
- Next steps
  - Send docs
```

**Enriched:**
```
Call with [[John]]
- Discussed [[AI project]]
  - Timeline looks good
- Next steps
  - Send docs
```

**Commit creates:**
```
Daily Note Page
└── Call with [[John]]
    ├── Discussed [[AI project]]
    │   └── Timeline looks good
    └── Next steps
        └── Send docs
```

## File Changes

| File | Changes |
|------|---------|
| `roam_api.py` | Add `batch_write()` method |
| `server.py` | Add `parse_multiline_note()`, `build_batch_actions()` |
| `server.py` | Add `QuickCaptureMultilineEnrich`, `QuickCaptureMultilineCommit` models |
| `server.py` | Add `quick_capture_multiline_enrich()`, `quick_capture_multiline_commit()` |
| `server.py` | Register new tools in `list_tools()` and `call_tool()` |
| `tests/` | Add tests for parsing and batch creation |
| `CLAUDE.md` | Document new tools |

## Edge Cases

1. **Empty lines**: Treat as block separators (don't create empty blocks)
2. **Inconsistent indentation**: Normalize to 2-space levels
3. **Tab characters**: Convert tabs to 2 spaces
4. **Very deep nesting**: Roam supports arbitrary depth, no limit needed
5. **Single line input**: Falls back to existing single-block behavior

## Performance

- Single API call for any number of blocks (batch-actions)
- Enrichment runs once per line (same optimization as single-line)
- No additional API calls compared to single-line capture

## Open Questions

1. **Should single-line tool also accept multi-line?** Could auto-detect and route internally
2. **Preview format**: How to display the tree structure to user before commit?
3. **Max blocks per batch**: Does Roam have a limit? (Test with 50+ blocks)

# [Roam Backend API (Beta)](https://roamresearch.com/#/app/developer-documentation/page/W4Po8pcHQ)

Official documentation for the Roam Research Backend API.

## Description

- For capturing to both unencrypted & encrypted graphs, use the Append API instead
- [Postman Public Workspace](https://www.postman.com/roamresearch/workspace/roam-research-backend-api/collection/27948971-ac6bd2a2-c0f0-4259-abc1-78bde0a01958) - interactive API testing
  - [Walkthrough video](https://www.loom.com/share/2f14c2331b65439a81632b9b94400160)
- Currently in Public Beta
- Report issues in the #developers channel in the [Roam Slack](https://join.slack.com/t/roamresearch/shared_invite/zt-1x2y9jkx1-KkSjlsWeTdfXy5H8hMB7tg) or via email to support@roamresearch.com

### Caveats

- Encrypted graphs don't work (and will not work in the future, except for maybe an append API)
- A request to a brand new graph will fail on the first request but the second request should go through

## Authentication

- Requests use graph-specific tokens for authentication
- Only graph owners/admins can create tokens
- Tokens start with `roam-graph-token-`
- Create and edit tokens from "API tokens" in the "Graph" tab in Settings

### How to pass tokens in requests

Pass tokens in the `X-Authorization` header, prefixed with `Bearer `:

```
X-Authorization: Bearer roam-graph-token-t_OjqgIAH1JZphzP4HxjJNad55lLFKpsqIM7x3bW
```

You can also use the `Authorization` header (more secure), but you must ensure your code/library:
1. Handles redirects properly
2. Passes the authorization header when redirect has been followed (not default behavior in most libraries)

### Token Roles

- **read+edit**: Full access to Backend API
- **read-only**: Read-only access to Backend API
- **append-only**: Only for Append API

## SDKs

Official SDKs available at [github.com/Roam-Research/backend-sdks](https://github.com/Roam-Research/backend-sdks):

- [TypeScript](https://www.npmjs.com/package/@roam-research/roam-api-sdk)
- [Clojure](https://github.com/Roam-Research/backend-sdks/tree/master/clojure)
- [Python](https://github.com/Roam-Research/backend-sdks/tree/master/python)
- [Java](https://github.com/Roam-Research/backend-sdks/tree/master/java)

## API Reference

**Base URL:** `https://api.roamresearch.com/`

---

### Query Endpoint

**`POST /api/graph/{graph-name}/q`**

Execute Datalog queries against the graph.

#### Request Body

```json
{
  "query": "[:find ?block-uid ?block-str :in $ ?search-string :where [?b :block/uid ?block-uid] [?b :block/string ?block-str] [(clojure.string/includes? ?block-str ?search-string)]]",
  "args": ["apple"]
}
```

#### cURL Example

```bash
curl -X POST "https://api.roamresearch.com/api/graph/MY-GRAPH/q" --location-trusted \
  -H "accept: application/json" \
  -H "X-Authorization: Bearer roam-graph-token-for-MY-GRAPH-1JN132hnXUYIfso22" \
  -H "Content-Type: application/json" \
  -d '{"query": "[:find ?block-uid ?block-str :in $ ?search-string :where [?b :block/uid ?block-uid] [?b :block/string ?block-str] [(clojure.string/includes? ?block-str ?search-string)]]", "args": ["apple"]}'
```

---

### Pull Endpoint

**`POST /api/graph/{graph-name}/pull`**

Retrieve entity data with a pull pattern.

#### Request Body

| Key | Description |
|-----|-------------|
| `eid` | Entity identifier (e.g., `[:block/uid "08-30-2022"]`) |
| `selector` | Pull pattern specifying which attributes to retrieve |

#### Example

```json
{
  "eid": "[:block/uid \"08-30-2022\"]",
  "selector": "[:block/uid :node/title :block/string {:block/children [:block/uid :block/string]} {:block/refs [:node/title :block/string :block/uid]}]"
}
```

#### cURL Example

```bash
curl -X POST "https://api.roamresearch.com/api/graph/MY-GRAPH/pull" --location-trusted \
  -H "accept: application/json" \
  -H "Authorization: Bearer roam-graph-token-for-MY-GRAPH-1JN132hnXUYIfso22" \
  -H "Content-Type: application/json" \
  -d '{"eid": "[:block/uid \"08-30-2022\"]", "selector": "[:block/uid :node/title :block/string {:block/children [:block/uid :block/string]} {:block/refs [:node/title :block/string :block/uid]}]"}'
```

---

### Pull Many Endpoint

**`POST /api/graph/{graph-name}/pull-many`**

Retrieve multiple entities at once.

#### Request Body

| Key | Description |
|-----|-------------|
| `eids` | Array of entity identifiers |
| `selector` | Pull pattern specifying which attributes to retrieve |

#### Example

```json
{
  "eids": "[[:block/uid \"08-30-2022\"] [:block/uid \"08-31-2022\"]]",
  "selector": "[:block/uid :node/title :block/string {:block/children [:block/uid :block/string]} {:block/refs [:node/title :block/string :block/uid]}]"
}
```

---

### Write Endpoint

**`POST /api/graph/{graph-name}/write`**

Single endpoint for all write operations. Differentiate actions by passing the action name in the `action` key.

---

## Write Actions

### create-block

Creates a new block at a specified location.

#### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `location.parent-uid` | Yes* | UID of parent block |
| `location.page-title` | Yes* | Alternative to parent-uid; page title string OR `{"daily-note-page": "MM-DD-YYYY"}` for daily notes |
| `location.order` | Yes | Position: integer or `"last"` |
| `block.string` | Yes | Block content |
| `block.uid` | No | Custom UID |
| `block.open` | No | Collapsed state |
| `block.heading` | No | Heading level (1, 2, or 3) |
| `block.text-align` | No | Text alignment: `"left"`, `"center"`, `"right"` |
| `block.children-view-type` | No | `"document"`, `"numbered"`, `"bulleted"` |
| `block.block-view-type` | No | Block view type |

*Either `parent-uid` or `page-title` is required

#### Example

```json
{
  "action": "create-block",
  "location": {
    "parent-uid": "09-28-2022",
    "order": "last"
  },
  "block": {
    "string": "new block created via the backend",
    "open": false,
    "heading": 2,
    "text-align": "right",
    "children-view-type": "document"
  }
}
```

#### Using page-title for Daily Notes

```json
{
  "action": "create-block",
  "location": {
    "page-title": {"daily-note-page": "07-29-2023"},
    "order": "last"
  },
  "block": {
    "string": "Block on daily note"
  }
}
```

---

### move-block

Move a block to a new location.

#### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `block.uid` | Yes | UID of block to move |
| `location.parent-uid` | Yes* | New parent UID |
| `location.page-title` | Yes* | Alternative to parent-uid |
| `location.order` | Yes | New position |

#### Example

```json
{
  "action": "move-block",
  "block": {
    "uid": "7yYBPW-WO"
  },
  "location": {
    "parent-uid": "09-27-2022",
    "order": 3
  }
}
```

---

### update-block

Update a block's content and/or properties.

#### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `block.uid` | Yes | UID of block to update |
| `block.string` | No | New content |
| `block.open` | No | Collapsed state |
| `block.heading` | No | Heading level |
| `block.text-align` | No | Text alignment |
| `block.children-view-type` | No | Children view type |
| `block.block-view-type` | No | Block view type |

#### Example

```json
{
  "action": "update-block",
  "block": {
    "uid": "51v-orCLm",
    "string": "new string from the backend",
    "open": false,
    "heading": 2,
    "text-align": "center",
    "children-view-type": "numbered"
  }
}
```

---

### delete-block

Delete a block and all its children.

#### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `block.uid` | Yes | UID of block to delete |

#### Example

```json
{
  "action": "delete-block",
  "block": {
    "uid": "7yYBPW-WO"
  }
}
```

---

### create-page

Create a new page with a given title.

#### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `page.title` | Yes | Page title (format `January 21st, 2021` creates daily note) |
| `page.uid` | No | Custom UID |
| `page.children-view-type` | No | Children view type |

#### Example

```json
{
  "action": "create-page",
  "page": {
    "title": "List of participants",
    "children-view-type": "numbered"
  }
}
```

---

### update-page

Update a page's title and/or properties.

#### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `page.uid` | Yes | Page UID |
| `page.title` | No | New title |
| `page.children-view-type` | No | Children view type |

#### Example

```json
{
  "action": "update-page",
  "page": {
    "uid": "xK98D8L7U",
    "title": "List of participants (updated)"
  }
}
```

---

### delete-page

Delete a page and all its children blocks.

#### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `page.uid` | Yes | Page UID |

#### Example

```json
{
  "action": "delete-page",
  "page": {
    "uid": "xK98D8L7U"
  }
}
```

---

### batch-actions

Execute multiple write actions in a single request, in order.

#### Request Format

```json
{
  "action": "batch-actions",
  "actions": [
    {
      "action": "create-page",
      "page": { "title": "Batch action test page", "uid": -1 }
    },
    {
      "action": "create-block",
      "location": { "parent-uid": -1, "order": "last" },
      "block": { "string": "First" }
    },
    {
      "action": "create-block",
      "location": { "parent-uid": -1, "order": "last" },
      "block": { "string": "Second", "uid": -2 }
    },
    {
      "action": "move-block",
      "block": { "uid": -2 },
      "location": { "parent-uid": -1, "order": 1 }
    }
  ]
}
```

#### Temporary IDs (tempids)

Instead of actual UID strings, you can pass negative integers and reuse them across a batch. The response will include a mapping:

```json
{
  "tempids-to-uids": {
    "-1": "EBiw8LzPb",
    "-2": "X4DelKvsP"
  }
}
```

#### Error Handling

On failure, actions are validated first, then executed in sequence. If an error occurs:
- First `x` actions may succeed
- Remaining `n-x` actions will not execute

Response body on error contains:
- `message`: Specific error that occurred
- `num-actions-successfully-transacted-before-failure`: Number of successful actions before failure
- `batch-error-message`: Higher-level description of what went wrong

---

## HTTP Response Codes

| Code | Description |
|------|-------------|
| **200 OK** | Request successful |
| **308 Permanent Redirect** | Follow redirect to actual API server |
| **400 Bad Request** | Invalid input, encrypted graph, invalid action, token issues |
| **401 Unauthorized** | Not authenticated or insufficient permissions |
| **404 Not Found** | Invalid API route |
| **429 Too Many Requests** | Rate limit exceeded (50 requests/minute/graph) |
| **500 Internal Server Error** | Server error; check `message` field. "took too long to run" means query timeout (20 seconds) |
| **503 Service Unavailable** | Graph not ready; retry later |

---

## Rate Limits

- **50 requests per minute per graph**
- Use `batch-actions` to reduce request count
- Returns `429 Too Many Requests` when limit exceeded

---

## FAQ

### How do I handle `--location-trusted` in languages other than cURL?

Two requirements:
1. **Automatically follow redirects** (usually default)
2. **Pass authorization header on redirect** (usually NOT default)

Alternative: Use `X-Authorization` header instead of `Authorization` header.

#### Python Examples

See [Matt Vogel's examples](https://gist.github.com/8bitgentleman/75561ac116b5b925fd58ff595389d591)

#### Postman Setup

1. Enable "Automatically follow redirects" in settings
2. Enable "Follow Authorization Header" in request-level settings

### Can I use the API from browser JavaScript (roam/js)?

No, this is not currently possible due to CORS and preflight request issues. Client-side API functions may be exposed in the Roam Alpha API in the future.

---

## Changelog

### April 30th, 2024
- Released `pull-many` endpoint
- Added proper documentation for all error codes

### March 7th, 2024
- Better error reporting for `batch-actions`: now returns `num-actions-successfully-transacted-before-failure`

### July 29th, 2023
- Added `page-title` parameter for `create-block` and `move-block` actions
- Supports daily notes via `{"daily-note-page": "MM-DD-YYYY"}` format

### November 23rd, 2022
- **Breaking change**: Keys in pull/query results now have `:` prefix (e.g., `:block/string` instead of `block/string`)
- More secure API tokens (secret only visible at creation time)
- Graph-specific usage quotas introduced

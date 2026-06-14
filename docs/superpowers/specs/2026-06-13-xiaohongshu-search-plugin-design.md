# Xiaohongshu Search Plugin Design

## Goal

Add an internal plugin that lets the agent search Xiaohongshu note results
through `xiaohongshu-mcp` by default, filter results against user requirements,
sort them newest first, and return a reply-ready list of links. A compatible
HTTP JSON endpoint remains supported for user-owned adapters.

## Data Source

The plugin does not scrape Xiaohongshu directly and does not store browser
cookies or login state. The default endpoint is:

```text
http://localhost:18060/mcp
```

For this endpoint, the plugin uses MCP Streamable HTTP: it initializes a
session, carries the returned `Mcp-Session-Id`, and calls the `search_feeds`
tool with `sort_by = "最新"`.

The `xiaohongshu-mcp` process owns browser cookies and login state under its
ignored local data directory. The plugin only receives tool results. A
configured non-MCP endpoint may be a third-party search API or a user-owned
adapter service; it may return either a list of items or an object with an
`items` list. An optional configured API key is sent as a bearer token.

## Tool

Register `search_xiaohongshu_posts` with arguments:

- `query`: required search query.
- `require_keywords`: optional keywords that must appear in title/content.
- `exclude_keywords`: optional keywords that must not appear in title/content.
- `limit`: number of links to return, default 10, maximum 20.
- `publish_time`: optional Xiaohongshu time filter.
- `note_type`: optional Xiaohongshu note-type filter.

The tool returns:

- `items`: normalized post data sorted by published time descending.
- `text`: newline-delimited reply text, each line containing date, title, and
  URL.

## Normalization

Each raw item or MCP feed card may use common field aliases:

- title: `title`, `displayTitle`, `display_title`, or `desc`
- URL: `url`, `link`, or `share_link`
- timestamp: `published_at`, `time`, `timestamp`, `create_time`, or `date`
- content: `content`, `summary`, `desc`, or `text`

Timestamps can be ISO strings, Unix seconds, Unix milliseconds, or
`YYYY-MM-DD HH:MM:SS`. Missing timestamps are sorted after dated results.
For MCP feed cards without an explicit URL, the plugin builds an explore URL
from the feed ID and `xsecToken`.

## Filtering

Filtering is local and deterministic:

- All `require_keywords` must appear in the combined title/content text.
- Any `exclude_keywords` match removes the item.
- Items without a URL are ignored because the user asked for links.

## Runtime Wiring

`AppRuntime` loads the plugin as a built-in plugin alongside
`group_messages`. The plugin registers its tool at dry-run and runtime startup.

## Errors And Login Boundary

- Connection failures explain how to start `xiaohongshu-mcp`.
- Request timeouts explain that Xiaohongshu may still require QR login.
- MCP tool errors are returned directly instead of asking the LLM to guess.
- The plugin does not create, read, or commit Xiaohongshu cookies.
- Empty filtered results return success with an empty `items` list and a clear
  `text` message.

## Verification

- Tool loads in `AppRuntime.dry_run()`.
- MCP initialize/session handling is covered by a fake transport test.
- MCP feed cards and compatible JSON endpoint responses are normalized,
  filtered, sorted newest first, and formatted as links.
- Connection and timeout failures return actionable errors.
- URL-less results are skipped.
- `git diff --check`, sensitive scan, and full pytest pass before completion.

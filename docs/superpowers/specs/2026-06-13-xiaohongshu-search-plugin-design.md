# Xiaohongshu Search Plugin Design

## Goal

Add an internal plugin that lets the agent search Xiaohongshu-like note results
from a configured HTTP JSON search endpoint, filter results against user
requirements, sort them newest first, and return a reply-ready list of links.

## Data Source

The plugin does not scrape Xiaohongshu directly and does not store browser
cookies or login state. It calls a configured JSON endpoint:

- `XHS_SEARCH_ENDPOINT`: required URL.
- `XHS_SEARCH_API_KEY`: optional bearer token.

The endpoint may be a third-party search API or a user-owned adapter service.
The plugin sends query parameters and expects either a list of items or an
object with an `items` list.

## Tool

Register `search_xiaohongshu_posts` with arguments:

- `query`: required search query.
- `require_keywords`: optional keywords that must appear in title/content.
- `exclude_keywords`: optional keywords that must not appear in title/content.
- `limit`: number of links to return, default 10, maximum 20.

The tool returns:

- `items`: normalized post data sorted by published time descending.
- `text`: newline-delimited reply text, each line containing date, title, and
  URL.

## Normalization

Each raw item may use common field aliases:

- title: `title` or `desc`
- URL: `url`, `link`, or `share_link`
- timestamp: `published_at`, `time`, `timestamp`, `create_time`, or `date`
- content: `content`, `summary`, `desc`, or `text`

Timestamps can be ISO strings, Unix seconds, Unix milliseconds, or
`YYYY-MM-DD HH:MM:SS`. Missing timestamps are sorted after dated results.

## Filtering

Filtering is local and deterministic:

- All `require_keywords` must appear in the combined title/content text.
- Any `exclude_keywords` match removes the item.
- Items without a URL are ignored because the user asked for links.

## Runtime Wiring

`AppRuntime` loads the plugin as a built-in plugin alongside
`group_messages`. The plugin registers its tool at dry-run and runtime startup.

## Errors

- Missing `XHS_SEARCH_ENDPOINT` returns a tool error explaining the required
  environment variable.
- Endpoint HTTP failures are returned as tool errors.
- Empty filtered results return success with an empty `items` list and a clear
  `text` message.

## Verification

- Tool loads in `AppRuntime.dry_run()`.
- A fake endpoint response is normalized, filtered, sorted newest first, and
  formatted as links.
- Missing endpoint returns a tool error.
- URL-less results are skipped.
- `git diff --check`, sensitive scan, and full pytest pass before completion.

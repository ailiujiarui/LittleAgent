import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field

from mini_agent.plugins.context import PluginContext
from mini_agent.tools.base import Tool, ToolResult


MAX_RESULTS = 20
Fetcher = Callable[["SearchXiaohongshuPostsArgs", Dict[str, str]], Awaitable[Iterable[Dict[str, Any]]]]


class SearchXiaohongshuPostsArgs(BaseModel):
    query: str
    require_keywords: List[str] = Field(default_factory=list)
    exclude_keywords: List[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1)


def create_setup(
    fetcher: Optional[Fetcher] = None,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
):
    def setup(ctx: PluginContext) -> None:
        async def search(args: SearchXiaohongshuPostsArgs):
            settings = _settings(endpoint=endpoint, api_key=api_key)
            if not settings["endpoint"]:
                raise ValueError("XHS_SEARCH_ENDPOINT is required for Xiaohongshu search")

            raw_items = await (fetcher or _fetch_http)(args, settings)
            items = _select_items(raw_items, args)
            text = _format_reply(items)
            return ToolResult(
                success=True,
                content={"items": items},
                text=text,
            )

        ctx.register_tool(
            Tool(
                "search_xiaohongshu_posts",
                "Search Xiaohongshu posts from a configured JSON endpoint and return newest links first.",
                SearchXiaohongshuPostsArgs,
                search,
            )
        )

    return setup


def setup(ctx: PluginContext) -> None:
    create_setup()(ctx)


def _settings(endpoint: Optional[str], api_key: Optional[str]) -> Dict[str, str]:
    return {
        "endpoint": endpoint if endpoint is not None else os.environ.get("XHS_SEARCH_ENDPOINT", ""),
        "api_key": api_key if api_key is not None else os.environ.get("XHS_SEARCH_API_KEY", ""),
    }


async def _fetch_http(
    args: SearchXiaohongshuPostsArgs,
    settings: Dict[str, str],
) -> Iterable[Dict[str, Any]]:
    import httpx

    headers = {}
    if settings["api_key"]:
        headers["Authorization"] = f"Bearer {settings['api_key']}"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            settings["endpoint"],
            params={"q": args.query, "query": args.query, "limit": args.limit},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        return []
    return data


def _select_items(
    raw_items: Iterable[Dict[str, Any]],
    args: SearchXiaohongshuPostsArgs,
) -> List[Dict[str, Any]]:
    items = []
    for raw in raw_items:
        item = _normalize_item(raw)
        if not item["url"]:
            continue
        searchable = f"{item['title']} {item['content']}".lower()
        if any(keyword.lower() not in searchable for keyword in args.require_keywords):
            continue
        if any(keyword.lower() in searchable for keyword in args.exclude_keywords):
            continue
        items.append(item)
    items.sort(key=lambda item: item["_sort_time"], reverse=True)
    return [_public_item(item) for item in items[: min(args.limit, MAX_RESULTS)]]


def _normalize_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    title = _first_text(raw, ("title", "desc"))
    url = _first_text(raw, ("url", "link", "share_link"))
    content = _first_text(raw, ("content", "summary", "desc", "text"))
    published_at, sort_time = _parse_time(
        raw.get("published_at")
        or raw.get("time")
        or raw.get("timestamp")
        or raw.get("create_time")
        or raw.get("date")
    )
    return {
        "title": title,
        "url": url,
        "content": content,
        "published_at": published_at,
        "_sort_time": sort_time,
    }


def _first_text(raw: Dict[str, Any], names: Iterable[str]) -> str:
    for name in names:
        value = raw.get(name)
        if value is not None:
            return str(value).strip()
    return ""


def _parse_time(value: Any):
    if value in (None, ""):
        return "", 0.0
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return dt.date().isoformat(), timestamp

    text = str(value).strip()
    normalized = text.replace("Z", "+00:00")
    for candidate in (normalized, normalized.replace(" ", "T")):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.date().isoformat(), dt.timestamp()
        except ValueError:
            pass
    return text, 0.0


def _public_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": item["title"],
        "url": item["url"],
        "published_at": item["published_at"],
        "content": item["content"],
    }


def _format_reply(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "没有找到符合要求的小红书帖子链接。"
    lines = []
    for item in items:
        date = item["published_at"] or "unknown-date"
        title = item["title"] or "untitled"
        lines.append(f"{date} {title} {item['url']}")
    return "\n".join(lines)

import json
import os
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional
from urllib.parse import quote, urlencode, urlparse

from pydantic import BaseModel, Field

from mini_agent.plugins.context import PluginContext
from mini_agent.tools.base import Tool, ToolResult


MAX_RESULTS = 20
DEFAULT_MCP_ENDPOINT = "http://localhost:18060/mcp"
MCP_TIMEOUT_SECONDS = 45
MCP_PROTOCOL_VERSION = "2025-03-26"

Fetcher = Callable[["SearchXiaohongshuPostsArgs", Dict[str, str]], Awaitable[Iterable[Dict[str, Any]]]]
MCPTransport = Callable[
    [str, Dict[str, Any], Dict[str, str], int],
    Awaitable[Dict[str, Any]],
]


class SearchXiaohongshuPostsArgs(BaseModel):
    query: str
    require_keywords: List[str] = Field(default_factory=list)
    exclude_keywords: List[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1)
    publish_time: str = Field(
        default="",
        description="Xiaohongshu publish time filter: 不限/一天内/一周内/半年内, or aliases like last day/last week.",
    )
    note_type: str = Field(
        default="",
        description="Xiaohongshu note type filter: 不限/视频/图文.",
    )


def create_setup(
    fetcher: Optional[Fetcher] = None,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    mcp_transport: Optional[MCPTransport] = None,
):
    def setup(ctx: PluginContext) -> None:
        async def search(args: SearchXiaohongshuPostsArgs):
            settings = _settings(endpoint=endpoint, api_key=api_key)
            if not settings["endpoint"] and fetcher is None:
                raise ValueError("XHS_SEARCH_ENDPOINT is required for Xiaohongshu search")

            if fetcher is not None:
                raw_items = await fetcher(args, settings)
            elif _looks_like_mcp_endpoint(settings["endpoint"]):
                raw_items = await _fetch_xiaohongshu_mcp(args, settings, mcp_transport)
            else:
                raw_items = await _fetch_http(args, settings)

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
                _tool_description(endpoint),
                SearchXiaohongshuPostsArgs,
                search,
            )
        )

    return setup


def setup(ctx: PluginContext) -> None:
    create_setup()(ctx)


def _tool_description(endpoint: Optional[str]) -> str:
    description = (
        "Search Xiaohongshu posts via xiaohongshu-mcp search_feeds or a "
        "configured JSON endpoint, then return newest links first."
    )
    configured_endpoint = endpoint if endpoint is not None else os.environ.get(
        "XHS_SEARCH_ENDPOINT",
        DEFAULT_MCP_ENDPOINT,
    )
    if configured_endpoint:
        return f"{description} Configured endpoint: {configured_endpoint}"
    return description


def _settings(endpoint: Optional[str], api_key: Optional[str]) -> Dict[str, str]:
    configured_endpoint = endpoint if endpoint is not None else os.environ.get(
        "XHS_SEARCH_ENDPOINT",
        DEFAULT_MCP_ENDPOINT,
    )
    return {
        "endpoint": configured_endpoint,
        "api_key": api_key if api_key is not None else os.environ.get("XHS_SEARCH_API_KEY", ""),
    }


def _looks_like_mcp_endpoint(endpoint: str) -> bool:
    return urlparse(endpoint).path.rstrip("/").endswith("/mcp")


async def _fetch_xiaohongshu_mcp(
    args: SearchXiaohongshuPostsArgs,
    settings: Dict[str, str],
    transport: Optional[MCPTransport],
) -> Iterable[Dict[str, Any]]:
    post = transport or _post_mcp_json
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if settings["api_key"]:
        headers["Authorization"] = f"Bearer {settings['api_key']}"

    try:
        initialized = await post(
            settings["endpoint"],
            _build_mcp_initialize_payload(),
            headers,
            MCP_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        raise ValueError(_mcp_transport_error_message(exc, phase="连接")) from exc

    session_id = _mcp_session_id(initialized)
    if session_id:
        headers = {**headers, "Mcp-Session-Id": session_id}

    try:
        response = await post(
            settings["endpoint"],
            _build_mcp_search_payload(args),
            headers,
            MCP_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        raise ValueError(_mcp_transport_error_message(exc, phase="请求")) from exc
    return _extract_mcp_items(_mcp_body(response))


def _build_mcp_initialize_payload() -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {
                "name": "mini-agent",
                "version": "0.1.0",
            },
        },
    }


def _mcp_body(response: Dict[str, Any]) -> Dict[str, Any]:
    body = response.get("body") if isinstance(response, dict) else None
    if isinstance(body, dict):
        return body
    return response


def _mcp_session_id(response: Dict[str, Any]) -> str:
    if not isinstance(response, dict):
        return ""
    headers = response.get("headers")
    if not isinstance(headers, dict):
        return ""
    for key, value in headers.items():
        if str(key).lower() == "mcp-session-id":
            return str(value)
    return ""


def _mcp_transport_error_message(exc: Exception, phase: str) -> str:
    raw = str(exc).strip()
    if "All connection attempts failed" in raw or "ConnectError" in type(exc).__name__:
        return (
            "xiaohongshu-mcp 连接失败：请确认服务已启动并监听 http://localhost:18060/mcp。"
            "可在 docker/xiaohongshu-mcp 目录执行 .\\start.ps1。"
        )
    if not raw or "ReadTimeout" in type(exc).__name__ or "timed out" in raw.lower():
        return (
            f"xiaohongshu-mcp {phase}超时：服务已连接但没有及时返回。"
            "常见原因是尚未扫码登录小红书，或登录浏览器正在等待扫码；"
            "请先通过 get_login_qrcode 获取二维码并扫码登录。"
        )
    return f"xiaohongshu-mcp {phase}失败：{raw}"


async def _post_mcp_json(
    endpoint: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        return {
            "headers": dict(response.headers),
            "body": response.json(),
        }


def _build_mcp_search_payload(args: SearchXiaohongshuPostsArgs) -> Dict[str, Any]:
    filters: Dict[str, str] = {"sort_by": "最新"}
    publish_time = _normalize_publish_time(args.publish_time)
    note_type = _normalize_note_type(args.note_type)
    if publish_time:
        filters["publish_time"] = publish_time
    if note_type:
        filters["note_type"] = note_type

    return {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "search_feeds",
            "arguments": {
                "keyword": args.query,
                "filters": filters,
            },
        },
    }


def _extract_mcp_items(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    if response.get("error"):
        raise ValueError(f"xiaohongshu-mcp error: {response['error']}")

    result = response.get("result") if isinstance(response, dict) else None
    if not isinstance(result, dict):
        return []
    if result.get("isError"):
        raise ValueError(_text_from_content(result.get("content", [])) or "xiaohongshu-mcp tool failed")

    items: List[Dict[str, Any]] = []
    for block in result.get("content", []):
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        data = _parse_json_text(block.get("text", ""))
        items.extend(_extract_items_from_payload(data))
    return items


def _parse_json_text(text: str) -> Any:
    stripped = str(text or "").strip()
    if not stripped:
        return {}
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError("xiaohongshu-mcp returned non-JSON text content") from exc


def _extract_items_from_payload(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    for key in ("items", "feeds", "data", "result"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_items_from_payload(value)
            if nested:
                return nested

    return []


def _text_from_content(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


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
    for index, raw in enumerate(raw_items):
        item = _normalize_item(raw, index)
        if not item["url"]:
            continue
        searchable = f"{item['title']} {item['content']}".lower()
        if any(keyword.lower() not in searchable for keyword in args.require_keywords):
            continue
        if any(keyword.lower() in searchable for keyword in args.exclude_keywords):
            continue
        items.append(item)
    items.sort(key=lambda item: (item["_sort_time"], -item["_source_index"]), reverse=True)
    return [_public_item(item) for item in items[: min(args.limit, MAX_RESULTS)]]


def _normalize_item(raw: Dict[str, Any], index: int = 0) -> Dict[str, Any]:
    note_card = _dict_value(raw, "noteCard", "note_card", "card")
    title = (
        _first_text(raw, ("title", "displayTitle", "display_title", "desc"))
        or _first_text(note_card, ("displayTitle", "display_title", "title", "desc"))
    )
    content = (
        _first_text(raw, ("content", "summary", "desc", "text"))
        or _first_text(note_card, ("content", "summary", "desc", "text"))
    )
    url = _first_text(raw, ("url", "link", "share_link", "shareLink"))
    if not url:
        url = _feed_url(raw)

    published_at, sort_time = _parse_time(
        raw.get("published_at")
        or raw.get("publish_time")
        or raw.get("time")
        or raw.get("timestamp")
        or raw.get("create_time")
        or raw.get("date")
        or note_card.get("time")
        or note_card.get("timestamp")
        or note_card.get("create_time")
    )
    return {
        "title": title,
        "url": url,
        "content": content,
        "published_at": published_at,
        "_sort_time": sort_time,
        "_source_index": index,
    }


def _feed_url(raw: Dict[str, Any]) -> str:
    feed_id = _first_text(raw, ("id", "feed_id", "noteId", "note_id"))
    if not feed_id:
        return ""
    params: Dict[str, str] = {}
    xsec_token = _first_text(raw, ("xsecToken", "xsec_token"))
    if xsec_token:
        params["xsec_token"] = xsec_token
    query = f"?{urlencode(params)}" if params else ""
    return f"https://www.xiaohongshu.com/explore/{quote(feed_id, safe='')}{query}"


def _dict_value(raw: Dict[str, Any], *names: str) -> Dict[str, Any]:
    for name in names:
        value = raw.get(name)
        if isinstance(value, dict):
            return value
    return {}


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

    chinese_date = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if chinese_date:
        year, month, day = (int(part) for part in chinese_date.groups())
        dt = datetime(year, month, day, tzinfo=timezone.utc)
        return dt.date().isoformat(), dt.timestamp()

    iso_date = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if iso_date:
        year, month, day = (int(part) for part in iso_date.groups())
        dt = datetime(year, month, day, tzinfo=timezone.utc)
        return dt.date().isoformat(), dt.timestamp()

    return text, 0.0


def _normalize_publish_time(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    aliases = {
        "unlimited": "不限",
        "any": "不限",
        "all": "不限",
        "不限": "不限",
        "last day": "一天内",
        "one day": "一天内",
        "today": "一天内",
        "一天内": "一天内",
        "1天内": "一天内",
        "last week": "一周内",
        "one week": "一周内",
        "week": "一周内",
        "一周内": "一周内",
        "7天内": "一周内",
        "last 6 months": "半年内",
        "six months": "半年内",
        "half year": "半年内",
        "半年内": "半年内",
    }
    return aliases.get(text, value)


def _normalize_note_type(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    aliases = {
        "all": "不限",
        "any": "不限",
        "unlimited": "不限",
        "不限": "不限",
        "video": "视频",
        "视频": "视频",
        "image": "图文",
        "images": "图文",
        "note": "图文",
        "图文": "图文",
    }
    return aliases.get(text, value)


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


def _extract_public_search_results(html: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for anchor_match in re.finditer(
        r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<title>.*?)</a>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        href = unescape(anchor_match.group("href"))
        if "xiaohongshu.com/" not in href:
            continue
        title = _strip_html(anchor_match.group("title"))
        after = html[anchor_match.end() : anchor_match.end() + 600]
        content = _strip_html(after)
        date_text = _extract_date_text(content)
        items.append(
            {
                "title": title,
                "url": href,
                "content": content,
                "published_at": date_text,
            }
        )
    return items


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_date_text(text: str) -> str:
    for pattern in (
        r"\d{4}-\d{1,2}-\d{1,2}",
        r"\d{4}年\d{1,2}月\d{1,2}日",
    ):
        match = re.search(pattern, text)
        if match:
            date, _ = _parse_time(match.group(0))
            return date
    return ""

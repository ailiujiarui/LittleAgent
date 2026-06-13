from typing import Any, Dict, Iterable, List

from pydantic import BaseModel


class SourceItem(BaseModel):
    source: str
    key: str
    title: str
    url: str = ""
    content: str = ""


def normalize_json_items(source_name: str, raw_items: Iterable[Dict[str, Any]]) -> List[SourceItem]:
    items = []
    for index, item in enumerate(raw_items):
        key = str(item.get("id") or item.get("key") or item.get("url") or index)
        items.append(
            SourceItem(
                source=source_name,
                key=key,
                title=str(item.get("title") or ""),
                url=str(item.get("url") or item.get("link") or ""),
                content=str(item.get("summary") or item.get("content") or item.get("text") or ""),
            )
        )
    return items


class HTTPJSONSource:
    def __init__(self, name: str, url: str) -> None:
        self.name = name
        self.url = url

    async def fetch(self) -> List[SourceItem]:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(self.url)
            response.raise_for_status()
            data = response.json()
        if isinstance(data, dict):
            data = data.get("items", [])
        return normalize_json_items(self.name, data)


class RSSSource:
    def __init__(self, name: str, url: str) -> None:
        self.name = name
        self.url = url

    async def fetch(self) -> List[SourceItem]:
        try:
            import feedparser
        except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency.
            raise RuntimeError("feedparser is required for RSSSource") from exc

        feed = feedparser.parse(self.url)
        return [
            SourceItem(
                source=self.name,
                key=str(entry.get("id") or entry.get("link") or entry.get("title")),
                title=str(entry.get("title") or ""),
                url=str(entry.get("link") or ""),
                content=str(entry.get("summary") or ""),
            )
            for entry in feed.entries
        ]

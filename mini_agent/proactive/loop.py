import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from pydantic import BaseModel

from mini_agent.db.migrations import apply_migrations
from mini_agent.proactive.sources import SourceItem
from mini_agent.tools.registry import ToolRegistry


class JudgeResult(BaseModel):
    score: float
    message: str


class ProactiveStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        apply_migrations(self.db_path)

    def has_seen(self, item: SourceItem) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                select 1 from proactive_items
                where source = ? and item_key = ?
                """,
                (item.source, item.key),
            ).fetchone()
        return row is not None

    def mark_seen(self, item: SourceItem) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                insert or ignore into proactive_items (source, item_key, title, url, judged_at)
                values (?, ?, ?, ?, current_timestamp)
                """,
                (item.source, item.key, item.title, item.url),
            )
            conn.commit()

    def mark_pushed(self, item: SourceItem) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                update proactive_items
                set pushed_at = current_timestamp
                where source = ? and item_key = ?
                """,
                (item.source, item.key),
            )
            conn.commit()

    def has_recent_push(self, cooldown_minutes: int) -> bool:
        if cooldown_minutes <= 0:
            return False
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                select 1 from proactive_items
                where pushed_at is not null
                  and pushed_at >= datetime('now', ?)
                limit 1
                """,
                (f"-{cooldown_minutes} minutes",),
            ).fetchone()
        return row is not None

    def today_push_count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                select count(*) from proactive_items
                where pushed_at is not null
                  and date(pushed_at) = date('now')
                """
            ).fetchone()
        return int(row[0])


class ProactiveLoop:
    def __init__(
        self,
        sources: Iterable[Any],
        judge: Any,
        store: ProactiveStore,
        tools: ToolRegistry,
        target_channel: str,
        target_chat_id: str,
        threshold: float = 0.65,
        cooldown_minutes: int = 30,
        daily_max_pushes: int = 8,
        is_session_busy: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self.sources = list(sources)
        self.judge = judge
        self.store = store
        self.tools = tools
        self.target_channel = target_channel
        self.target_chat_id = target_chat_id
        self.threshold = threshold
        self.cooldown_minutes = cooldown_minutes
        self.daily_max_pushes = daily_max_pushes
        self.is_session_busy = is_session_busy or (lambda session_key: False)

    async def tick(self) -> int:
        session_key = f"{self.target_channel}:{self.target_chat_id}"
        if self.is_session_busy(session_key):
            return 0
        if self.store.has_recent_push(self.cooldown_minutes):
            return 0
        if self.store.today_push_count() >= self.daily_max_pushes:
            return 0

        pushed = 0
        for source in self.sources:
            for item in await source.fetch():
                if self.store.has_seen(item):
                    continue
                self.store.mark_seen(item)
                decision = await self.judge.judge(item)
                if decision.score < self.threshold:
                    continue
                result = await self.tools.execute(
                    "message_push",
                    {
                        "channel": self.target_channel,
                        "chat_id": self.target_chat_id,
                        "text": decision.message,
                    },
                )
                if result.success:
                    self.store.mark_pushed(item)
                    pushed += 1
                if pushed and (
                    self.store.has_recent_push(self.cooldown_minutes)
                    or self.store.today_push_count() >= self.daily_max_pushes
                ):
                    return pushed
        return pushed


def parse_judge_json(text: str) -> JudgeResult:
    data = json.loads(text)
    return JudgeResult(score=float(data["score"]), message=str(data["message"]))

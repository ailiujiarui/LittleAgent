import json
import sqlite3
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List

from mini_agent.db.migrations import apply_migrations
from mini_agent.tools.base import Tool
from mini_agent.tools.registry import ToolRegistry


EventHandler = Callable[[Dict[str, Any]], Awaitable[None]]


class PluginKVStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        apply_migrations(self.db_path)

    def set(self, plugin_name: str, key: str, value: Any) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                insert into plugin_kv (plugin_name, key, value_json)
                values (?, ?, ?)
                on conflict(plugin_name, key) do update set
                    value_json = excluded.value_json,
                    updated_at = current_timestamp
                """,
                (plugin_name, key, json.dumps(value, ensure_ascii=False)),
            )
            conn.commit()

    def get(self, plugin_name: str, key: str, default: Any = None) -> Any:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                select value_json from plugin_kv
                where plugin_name = ? and key = ?
                """,
                (plugin_name, key),
            ).fetchone()
        if row is None:
            return default
        return json.loads(row[0])


class PluginContext:
    def __init__(
        self,
        name: str,
        workspace: Path,
        plugin_dir: Path,
        tools: ToolRegistry,
        kv_store: PluginKVStore,
        event_handlers: Dict[str, List[EventHandler]],
    ) -> None:
        self.name = name
        self.workspace = Path(workspace)
        self.plugin_dir = Path(plugin_dir)
        self.tools = tools
        self.kv_store = kv_store
        self._event_handlers = event_handlers

    def register_tool(self, tool: Tool) -> None:
        self.tools.register(tool, source_type="plugin", source_name=self.name)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        self._event_handlers.setdefault(event_name, []).append(handler)

    def kv_set(self, key: str, value: Any) -> None:
        self.kv_store.set(self.name, key, value)

    def kv_get(self, key: str, default: Any = None) -> Any:
        return self.kv_store.get(self.name, key, default)

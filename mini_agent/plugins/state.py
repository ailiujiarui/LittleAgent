import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from mini_agent.db.migrations import apply_migrations


@dataclass(frozen=True)
class PluginState:
    source: str
    name: str
    enabled: bool
    locked: bool
    last_loaded_at: Optional[str]
    last_error: str
    updated_at: str


class PluginStateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        apply_migrations(self.db_path)

    def ensure(
        self,
        source: str,
        name: str,
        *,
        default_enabled: bool,
        locked: bool = False,
    ) -> PluginState:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                insert into plugin_states (
                    source, name, enabled, locked, last_loaded_at, last_error, updated_at
                )
                values (?, ?, ?, ?, null, '', current_timestamp)
                on conflict(source, name) do nothing
                """,
                (source, name, int(default_enabled), int(locked)),
            )
            conn.commit()
        state = self.get(source, name)
        if state is None:
            raise RuntimeError(f"plugin state was not created: {source}:{name}")
        return state

    def get(self, source: str, name: str) -> Optional[PluginState]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                select source, name, enabled, locked, last_loaded_at, last_error, updated_at
                from plugin_states
                where source = ? and name = ?
                """,
                (source, name),
            ).fetchone()
        if row is None:
            return None
        return _row_to_state(row)

    def set_enabled(self, source: str, name: str, enabled: bool) -> PluginState:
        self.ensure(source, name, default_enabled=enabled)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                update plugin_states
                set enabled = ?, updated_at = current_timestamp
                where source = ? and name = ?
                """,
                (int(enabled), source, name),
            )
            conn.commit()
        return self._require_state(source, name)

    def set_loaded(self, source: str, name: str) -> PluginState:
        self.ensure(source, name, default_enabled=False)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                update plugin_states
                set last_loaded_at = current_timestamp,
                    last_error = '',
                    updated_at = current_timestamp
                where source = ? and name = ?
                """,
                (source, name),
            )
            conn.commit()
        return self._require_state(source, name)

    def set_error(self, source: str, name: str, error: str) -> PluginState:
        self.ensure(source, name, default_enabled=False)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                update plugin_states
                set last_error = ?, updated_at = current_timestamp
                where source = ? and name = ?
                """,
                (error, source, name),
            )
            conn.commit()
        return self._require_state(source, name)

    def _require_state(self, source: str, name: str) -> PluginState:
        state = self.get(source, name)
        if state is None:
            raise RuntimeError(f"plugin state does not exist: {source}:{name}")
        return state


def _row_to_state(row: sqlite3.Row) -> PluginState:
    return PluginState(
        source=row[0],
        name=row[1],
        enabled=bool(row[2]),
        locked=bool(row[3]),
        last_loaded_at=row[4],
        last_error=row[5],
        updated_at=row[6],
    )

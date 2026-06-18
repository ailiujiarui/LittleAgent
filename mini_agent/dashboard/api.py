import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from mini_agent.memory.store import WRITABLE_MEMORY_FILES, MemoryStore
from mini_agent.plugins.catalog import PluginCatalog, PluginSpec, builtin_plugin_specs
from mini_agent.plugins.manager import PluginActionResult, PluginManager, PluginSummary
from mini_agent.plugins.state import PluginState, PluginStateStore


AuthDependency = Callable[[Request], None]


class SaveMemoryRequest(BaseModel):
    content: str


def register_dashboard_api(
    app: FastAPI,
    workspace: Path,
    status: Optional[Dict[str, object]],
    require_auth: AuthDependency,
    plugin_manager: Optional[PluginManager] = None,
) -> None:
    workspace = Path(workspace)
    memory = MemoryStore(workspace)
    db_path = workspace / "agent.db"
    runtime_status = {"running": False, **(status or {})}
    auth_dependency = [Depends(require_auth)]

    @app.get("/api/status", dependencies=auth_dependency)
    def get_status():
        return {"workspace": str(workspace), **runtime_status}

    @app.get("/api/plugins", dependencies=auth_dependency)
    def list_plugins():
        if plugin_manager is not None:
            return {
                "mode": "runtime",
                "plugins": [
                    plugin.model_dump() for plugin in plugin_manager.list_plugins()
                ],
            }
        return {
            "mode": "standalone",
            "plugins": [
                plugin.model_dump()
                for plugin in _list_standalone_plugins(workspace)
            ],
        }

    @app.post("/api/plugins/{source}/{name}/enable", dependencies=auth_dependency)
    async def enable_plugin(source: str, name: str):
        if plugin_manager is not None:
            return _handle_runtime_action_result(
                await plugin_manager.enable(source, name)
            )
        return _standalone_action(workspace, source, name, "enable")

    @app.post("/api/plugins/{source}/{name}/disable", dependencies=auth_dependency)
    async def disable_plugin(source: str, name: str):
        if plugin_manager is not None:
            return _handle_runtime_action_result(
                await plugin_manager.disable(source, name)
            )
        return _standalone_action(workspace, source, name, "disable")

    @app.post("/api/plugins/{source}/{name}/reload", dependencies=auth_dependency)
    async def reload_plugin(source: str, name: str):
        if plugin_manager is not None:
            return _handle_runtime_action_result(
                await plugin_manager.reload(source, name)
            )
        return _standalone_action(workspace, source, name, "reload")

    @app.get("/api/memory/files", dependencies=auth_dependency)
    def list_memory_files():
        return {"files": sorted(WRITABLE_MEMORY_FILES)}

    @app.get("/api/memory/files/{name:path}", dependencies=auth_dependency)
    def read_memory_file(name: str):
        _validate_memory_name(name)
        return {"name": name, "content": memory.read_file(name)}

    @app.post("/api/memory/files/{name:path}", dependencies=auth_dependency)
    def write_memory_file(name: str, request: SaveMemoryRequest):
        _validate_memory_name(name)
        backup = _backup_memory_file(workspace, memory.memory_dir / name)
        memory.write_file(name, request.content)
        return {"saved": True, "backup": str(backup)}

    @app.get("/api/sessions", dependencies=auth_dependency)
    def list_sessions(limit: int = 50):
        limit = _clamp_limit(limit)
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                select
                    s.id,
                    s.channel,
                    s.chat_id,
                    s.created_at,
                    s.updated_at,
                    count(m.id) as message_count
                from sessions s
                left join messages m on m.session_id = s.id
                group by s.id, s.channel, s.chat_id, s.created_at, s.updated_at
                order by s.updated_at desc, s.id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return {
            "sessions": [
                {
                    "id": row[0],
                    "channel": row[1],
                    "chat_id": row[2],
                    "created_at": row[3],
                    "updated_at": row[4],
                    "message_count": int(row[5]),
                }
                for row in rows
            ]
        }

    @app.get("/api/sessions/{session_id:path}", dependencies=auth_dependency)
    def get_session(session_id: str):
        with sqlite3.connect(db_path) as conn:
            session = conn.execute(
                """
                select
                    s.id,
                    s.channel,
                    s.chat_id,
                    s.created_at,
                    s.updated_at,
                    count(m.id) as message_count
                from sessions s
                left join messages m on m.session_id = s.id
                where s.id = ?
                group by s.id, s.channel, s.chat_id, s.created_at, s.updated_at
                """,
                (session_id,),
            ).fetchone()
            if session is None:
                raise HTTPException(status_code=404, detail="会话不存在")

            messages = conn.execute(
                """
                select id, role, content, created_at
                from messages
                where session_id = ?
                order by id
                """,
                (session_id,),
            ).fetchall()

        return {
            "session": {
                "id": session[0],
                "channel": session[1],
                "chat_id": session[2],
                "created_at": session[3],
                "updated_at": session[4],
                "message_count": int(session[5]),
            },
            "messages": [
                {
                    "id": row[0],
                    "role": row[1],
                    "content": row[2],
                    "created_at": row[3],
                }
                for row in messages
            ],
        }

    @app.get("/api/events", dependencies=auth_dependency)
    def list_events(limit: int = 50):
        limit = _clamp_limit(limit)
        events: List[Dict[str, Any]] = []
        with sqlite3.connect(db_path) as conn:
            runtime_rows = conn.execute(
                """
                select id, event_type, payload_json, created_at
                from runtime_events
                order by created_at desc, id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
            tool_rows = conn.execute(
                """
                select id, session_id, tool_name, arguments_json, result_json, created_at
                from tool_events
                order by created_at desc, id desc
                limit ?
                """,
                (limit,),
            ).fetchall()

        for row in runtime_rows:
            events.append(
                {
                    "kind": "runtime",
                    "id": row[0],
                    "event_type": row[1],
                    "payload": _parse_json(row[2]),
                    "created_at": row[3],
                }
            )
        for row in tool_rows:
            events.append(
                {
                    "kind": "tool",
                    "id": row[0],
                    "session_id": row[1],
                    "tool_name": row[2],
                    "arguments": _parse_json(row[3]),
                    "result": _parse_json(row[4]),
                    "created_at": row[5],
                }
            )

        events.sort(key=lambda event: (event["created_at"], event["id"]), reverse=True)
        return {"events": events[:limit]}

    @app.get("/api/proactive", dependencies=auth_dependency)
    def list_proactive_items(limit: int = 50):
        limit = _clamp_limit(limit)
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                select id, source, item_key, title, url, judged_at, pushed_at
                from proactive_items
                order by id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return {
            "items": [
                {
                    "id": row[0],
                    "source": row[1],
                    "item_key": row[2],
                    "title": row[3],
                    "url": row[4],
                    "judged_at": row[5],
                    "pushed_at": row[6],
                }
                for row in rows
            ]
        }

    @app.get("/api/drift", dependencies=auth_dependency)
    def list_drift_runs(limit: int = 50):
        limit = _clamp_limit(limit)
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                select id, started_at, finished_at, status, summary
                from drift_runs
                order by id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return {
            "runs": [
                {
                    "id": row[0],
                    "started_at": row[1],
                    "finished_at": row[2],
                    "status": row[3],
                    "summary": row[4],
                }
                for row in rows
            ]
        }


def _validate_memory_name(name: str) -> None:
    if name not in WRITABLE_MEMORY_FILES or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="不支持的记忆文件")


def _backup_memory_file(workspace: Path, path: Path) -> Path:
    backup_dir = workspace / "backups" / "memory"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    backup_path = backup_dir / f"{path.name}.{stamp}.bak"
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), 200))


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        return {"raw": text}


def _list_standalone_plugins(workspace: Path) -> List[PluginSummary]:
    store = PluginStateStore(workspace / "agent.db")
    plugins = []
    for spec in _standalone_specs(workspace):
        state = store.ensure(
            spec.source,
            spec.name,
            default_enabled=spec.default_enabled,
            locked=spec.locked,
        )
        plugins.append(_standalone_summary(spec, state))
    return plugins


def _standalone_action(
    workspace: Path,
    source: str,
    name: str,
    action: str,
) -> PluginActionResult:
    spec = _find_standalone_spec(workspace, source, name)
    if spec is None:
        raise HTTPException(status_code=404, detail="插件不存在")

    store = PluginStateStore(workspace / "agent.db")
    state = store.ensure(
        source,
        name,
        default_enabled=spec.default_enabled,
        locked=spec.locked,
    )
    if action == "disable":
        if state.locked or spec.locked:
            raise HTTPException(status_code=400, detail="系统插件不可关闭")
        state = store.set_enabled(source, name, False)
    elif action == "enable":
        state = store.set_enabled(source, name, True)
    elif action == "reload":
        state = store.get(source, name) or state
    else:
        raise HTTPException(status_code=400, detail="不支持的插件操作")

    return PluginActionResult(
        ok=True,
        plugin=_standalone_summary(spec, state),
        requires_restart=True,
        message="已保存，Agent 下次启动后生效",
    )


def _handle_runtime_action_result(result: PluginActionResult) -> PluginActionResult:
    if result.message == "插件不存在":
        raise HTTPException(status_code=404, detail="插件不存在")
    if not result.ok and result.message == "系统插件不可关闭":
        raise HTTPException(status_code=400, detail="系统插件不可关闭")
    return result


def _standalone_specs(workspace: Path) -> List[PluginSpec]:
    return list(PluginCatalog(workspace, builtin_plugin_specs()).discover())


def _find_standalone_spec(
    workspace: Path,
    source: str,
    name: str,
) -> Optional[PluginSpec]:
    for spec in _standalone_specs(workspace):
        if spec.source == source and spec.name == name:
            return spec
    return None


def _standalone_summary(spec: PluginSpec, state: PluginState) -> PluginSummary:
    return PluginSummary(
        id=spec.id,
        source=spec.source,
        name=spec.name,
        enabled=state.enabled,
        loaded=False,
        locked=state.locked or spec.locked,
        tool_count=0,
        event_count=0,
        last_error=state.last_error,
        updated_at=state.updated_at,
    )

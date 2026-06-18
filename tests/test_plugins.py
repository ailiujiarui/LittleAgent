import asyncio
import sqlite3
import textwrap

import pytest
from pydantic import BaseModel


def _write_plugin(root, name, source):
    plugin_dir = root / "plugins" / name
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.py").write_text(textwrap.dedent(source), encoding="utf-8")
    return plugin_dir


def test_plugin_state_defaults_and_source_identity(tmp_path):
    from mini_agent.plugins.state import PluginStateStore

    store = PluginStateStore(tmp_path / "agent.db")

    builtin = store.ensure("builtin", "echo", default_enabled=True)
    workspace = store.ensure("workspace", "echo", default_enabled=False)

    assert builtin.source == "builtin"
    assert builtin.name == "echo"
    assert builtin.enabled is True
    assert builtin.locked is False
    assert workspace.source == "workspace"
    assert workspace.name == "echo"
    assert workspace.enabled is False
    assert workspace.locked is False
    assert store.get("builtin", "echo").enabled is True
    assert store.get("workspace", "echo").enabled is False
    assert store.get("workspace", "missing") is None


def test_plugin_state_updates_are_source_isolated(tmp_path):
    from mini_agent.plugins.state import PluginStateStore

    store = PluginStateStore(tmp_path / "agent.db")
    store.ensure("builtin", "echo", default_enabled=True)
    store.ensure("workspace", "echo", default_enabled=False)

    store.set_enabled("builtin", "echo", False)
    store.set_error("workspace", "echo", "workspace failed")

    builtin = store.get("builtin", "echo")
    workspace = store.get("workspace", "echo")

    assert builtin.enabled is False
    assert builtin.last_error == ""
    assert workspace.enabled is False
    assert workspace.last_error == "workspace failed"


def test_plugin_state_writes_touch_updated_at_and_fields(tmp_path):
    from mini_agent.plugins.state import PluginStateStore

    db_path = tmp_path / "agent.db"
    store = PluginStateStore(db_path)
    state = store.ensure("workspace", "echo", default_enabled=False)

    assert state.updated_at

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            update plugin_states set updated_at = '2000-01-01 00:00:00'
            where source = 'workspace' and name = 'echo'
            """
        )
        conn.commit()

    enabled = store.set_enabled("workspace", "echo", True)

    assert enabled.enabled is True
    assert enabled.updated_at != "2000-01-01 00:00:00"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            update plugin_states set updated_at = '2000-01-01 00:00:00'
            where source = 'workspace' and name = 'echo'
            """
        )
        conn.commit()

    loaded = store.set_loaded("workspace", "echo")

    assert loaded.last_loaded_at is not None
    assert loaded.last_error == ""
    assert loaded.updated_at != "2000-01-01 00:00:00"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            update plugin_states set updated_at = '2000-01-01 00:00:00'
            where source = 'workspace' and name = 'echo'
            """
        )
        conn.commit()

    failed = store.set_error("workspace", "echo", "boom")

    assert failed.last_error == "boom"
    assert failed.updated_at != "2000-01-01 00:00:00"


def test_plugin_context_kv_uses_stable_plugin_id_for_same_name_sources(tmp_path):
    from mini_agent.plugins.context import PluginContext, PluginKVStore
    from mini_agent.tools.registry import ToolRegistry

    db_path = tmp_path / "agent.db"
    kv_store = PluginKVStore(db_path)
    handlers = {}
    builtin = PluginContext(
        name="echo",
        plugin_id="builtin:echo",
        workspace=tmp_path,
        plugin_dir=tmp_path / "builtin",
        tools=ToolRegistry(),
        kv_store=kv_store,
        event_handlers=handlers,
    )
    workspace = PluginContext(
        name="echo",
        plugin_id="workspace:echo",
        workspace=tmp_path,
        plugin_dir=tmp_path / "plugins" / "echo",
        tools=ToolRegistry(),
        kv_store=kv_store,
        event_handlers=handlers,
    )

    builtin.kv_set("private", "builtin value")
    workspace.kv_set("private", "workspace value")

    assert builtin.kv_get("private") == "builtin value"
    assert workspace.kv_get("private") == "workspace value"

    with sqlite3.connect(db_path) as conn:
        plugin_names = {
            row[0]
            for row in conn.execute(
                "select plugin_name from plugin_kv order by plugin_name"
            ).fetchall()
        }

    assert plugin_names == {"builtin:echo", "workspace:echo"}


def test_plugin_catalog_discovers_builtin_and_workspace_plugins(tmp_path):
    from mini_agent.plugins.catalog import PluginCatalog, builtin_plugin_specs

    _write_plugin(tmp_path, "demo", "def setup(ctx): pass")

    catalog = PluginCatalog(tmp_path, builtin_plugin_specs())
    plugins = catalog.discover()
    identities = {(plugin.source, plugin.name, plugin.id) for plugin in plugins}

    assert ("builtin", "group_messages", "builtin:group_messages") in identities
    assert ("builtin", "xiaohongshu_search", "builtin:xiaohongshu_search") in identities
    assert ("workspace", "demo", "workspace:demo") in identities
    assert {
        (plugin.source, plugin.name): plugin.default_enabled for plugin in plugins
    }[("builtin", "group_messages")] is True
    assert {
        (plugin.source, plugin.name): plugin.default_enabled for plugin in plugins
    }[("workspace", "demo")] is False


def test_plugin_context_tracks_tools_events_and_uses_plugin_id_for_kv(tmp_path):
    from mini_agent.plugins.context import (
        PluginContext,
        PluginKVStore,
        PluginRegistrationTracker,
    )
    from mini_agent.tools.base import Tool
    from mini_agent.tools.registry import ToolRegistry

    class NoArgs(BaseModel):
        pass

    async def ok(args):
        return {"ok": True}

    registry = ToolRegistry()
    handlers = {}
    tracker = PluginRegistrationTracker()
    kv_store = PluginKVStore(tmp_path / "agent.db")
    ctx = PluginContext(
        name="echo",
        plugin_id="workspace:echo",
        workspace=tmp_path,
        plugin_dir=tmp_path / "plugins" / "echo",
        tools=registry,
        kv_store=kv_store,
        event_handlers=handlers,
        tracker=tracker,
    )

    async def on_event(event):
        return None

    ctx.register_tool(Tool("tracked_tool", "Tracked", NoArgs, ok))
    ctx.subscribe("turn_finished", on_event)
    ctx.kv_set("private", "workspace value")

    assert tracker.registered_tools == ["tracked_tool"]
    assert tracker.subscribed_events == [("turn_finished", on_event)]
    assert registry.unregister_source("plugin", "workspace:echo") == ["tracked_tool"]
    assert handlers["turn_finished"] == [on_event]
    assert ctx.kv_get("private") == "workspace value"


def test_plugin_manager_discovers_and_calls_setup_registering_tool(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.tools.registry import ToolRegistry

    _write_plugin(
        tmp_path,
        "echo_plugin",
        """
        from pydantic import BaseModel
        from mini_agent.tools.base import Tool

        class EchoArgs(BaseModel):
            text: str

        async def echo(args):
            return {"text": args.text}

        def setup(ctx):
            ctx.register_tool(Tool("plugin_echo", "Echo from plugin", EchoArgs, echo))
        """,
    )

    async def scenario():
        registry = ToolRegistry()
        manager = PluginManager(workspace=tmp_path, tools=registry)
        result = await manager.enable("workspace", "echo_plugin")
        executed = await registry.execute("plugin_echo", {"text": "hello"})

        assert result.ok is True
        assert result.plugin.loaded is True
        assert executed.content == {"text": "hello"}

    asyncio.run(scenario())


def test_plugin_event_handler_receives_event_and_can_use_kv(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.tools.registry import ToolRegistry

    _write_plugin(
        tmp_path,
        "observer",
        """
        def setup(ctx):
            async def on_turn_finished(event):
                ctx.kv_set("last_text", event["text"])
            ctx.subscribe("turn_finished", on_turn_finished)
        """,
    )

    async def scenario():
        manager = PluginManager(workspace=tmp_path, tools=ToolRegistry())
        await manager.enable("workspace", "observer")

        await manager.emit("turn_finished", {"text": "done"})

        assert manager.kv_get("observer", "last_text") == "done"

    asyncio.run(scenario())


def test_setup_failure_disables_only_that_plugin(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.tools.registry import ToolRegistry

    _write_plugin(
        tmp_path,
        "bad",
        """
        def setup(ctx):
            raise RuntimeError("broken")
        """,
    )
    _write_plugin(
        tmp_path,
        "good",
        """
        from pydantic import BaseModel
        from mini_agent.tools.base import Tool

        class NoArgs(BaseModel):
            pass

        async def ok(args):
            return {"ok": True}

        def setup(ctx):
            ctx.register_tool(Tool("good_tool", "Good", NoArgs, ok))
        """,
    )

    async def scenario():
        manager = PluginManager(workspace=tmp_path, tools=ToolRegistry())
        bad = await manager.enable("workspace", "bad")
        good = await manager.enable("workspace", "good")

        assert bad.ok is False
        assert bad.plugin.loaded is False
        assert "broken" in bad.plugin.last_error
        assert good.ok is True
        assert good.plugin.loaded is True
        assert manager.tools.has_tool("good_tool") is True

    asyncio.run(scenario())


def test_plugin_manager_loads_enabled_builtin_and_skips_new_workspace_plugin(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.tools.registry import ToolRegistry

    _write_plugin(
        tmp_path,
        "workspace_tool",
        """
        from pydantic import BaseModel
        from mini_agent.tools.base import Tool

        class NoArgs(BaseModel):
            pass

        def setup(ctx):
            ctx.register_tool(Tool("workspace_tool", "Workspace", NoArgs, lambda args: {}))
        """,
    )

    manager = PluginManager(
        workspace=tmp_path,
        tools=ToolRegistry(),
        builtin_plugins={"group_messages": lambda ctx: None},
    )
    result = manager.load_all()
    plugins = {plugin.id: plugin for plugin in manager.list_plugins()}

    assert result.loaded == ["group_messages"]
    assert manager.tools.has_tool("workspace_tool") is False
    assert plugins["builtin:group_messages"].enabled is True
    assert plugins["builtin:group_messages"].loaded is True
    assert plugins["workspace:workspace_tool"].enabled is False
    assert plugins["workspace:workspace_tool"].loaded is False


def test_plugin_disable_calls_teardown_and_removes_tools_and_events(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.tools.registry import ToolRegistry

    _write_plugin(
        tmp_path,
        "cleanup",
        """
        from pydantic import BaseModel
        from mini_agent.tools.base import Tool

        class NoArgs(BaseModel):
            pass

        def setup(ctx):
            ctx.kv_set("state", "loaded")
            async def on_event(event):
                ctx.kv_set("event", event["value"])
            ctx.subscribe("turn_finished", on_event)
            ctx.register_tool(Tool("cleanup_tool", "Cleanup", NoArgs, lambda args: {}))

        def teardown(ctx):
            ctx.kv_set("state", "torn down")
        """,
    )

    async def scenario():
        manager = PluginManager(workspace=tmp_path, tools=ToolRegistry())
        await manager.enable("workspace", "cleanup")

        disabled = await manager.disable("workspace", "cleanup")
        await manager.emit("turn_finished", {"value": "ignored"})

        assert disabled.ok is True
        assert disabled.plugin.enabled is False
        assert disabled.plugin.loaded is False
        assert manager.tools.has_tool("cleanup_tool") is False
        assert manager.kv_get("workspace:cleanup", "state") == "torn down"
        assert manager.kv_get("workspace:cleanup", "event") is None

    asyncio.run(scenario())


def test_plugin_setup_failure_rolls_back_registered_tool_and_event(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.tools.registry import ToolRegistry

    _write_plugin(
        tmp_path,
        "bad_partial",
        """
        from pydantic import BaseModel
        from mini_agent.tools.base import Tool

        class NoArgs(BaseModel):
            pass

        def setup(ctx):
            async def on_event(event):
                ctx.kv_set("event", "should not run")
            ctx.subscribe("turn_finished", on_event)
            ctx.register_tool(Tool("bad_partial_tool", "Bad", NoArgs, lambda args: {}))
            raise RuntimeError("boom")
        """,
    )

    async def scenario():
        manager = PluginManager(workspace=tmp_path, tools=ToolRegistry())

        result = await manager.enable("workspace", "bad_partial")
        await manager.emit("turn_finished", {})

        assert result.ok is False
        assert result.plugin.loaded is False
        assert "boom" in result.plugin.last_error
        assert manager.tools.has_tool("bad_partial_tool") is False
        assert manager.kv_get("workspace:bad_partial", "event") is None

    asyncio.run(scenario())


def test_plugin_teardown_error_is_recorded_but_cleanup_still_happens(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.tools.registry import ToolRegistry

    _write_plugin(
        tmp_path,
        "bad_teardown",
        """
        from pydantic import BaseModel
        from mini_agent.tools.base import Tool

        class NoArgs(BaseModel):
            pass

        def setup(ctx):
            ctx.register_tool(Tool("bad_teardown_tool", "Bad teardown", NoArgs, lambda args: {}))

        def teardown(ctx):
            raise RuntimeError("teardown boom")
        """,
    )

    async def scenario():
        manager = PluginManager(workspace=tmp_path, tools=ToolRegistry())
        await manager.enable("workspace", "bad_teardown")

        result = await manager.disable("workspace", "bad_teardown")

        assert result.ok is True
        assert result.plugin.loaded is False
        assert "teardown boom" in result.plugin.last_error
        assert manager.tools.has_tool("bad_teardown_tool") is False

    asyncio.run(scenario())


def test_plugin_reload_tears_down_old_plugin_and_loads_updated_code(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.tools.registry import ToolRegistry

    plugin_dir = _write_plugin(
        tmp_path,
        "reloadable",
        """
        from pydantic import BaseModel
        from mini_agent.tools.base import Tool

        class NoArgs(BaseModel):
            pass

        def setup(ctx):
            ctx.kv_set("version", "one")
            ctx.register_tool(Tool("reload_tool_v1", "V1", NoArgs, lambda args: {"version": "one"}))

        def teardown(ctx):
            ctx.kv_set("torn_down", "yes")
        """,
    )

    async def scenario():
        manager = PluginManager(workspace=tmp_path, tools=ToolRegistry())
        await manager.enable("workspace", "reloadable")
        (plugin_dir / "plugin.py").write_text(
            textwrap.dedent(
                """
                from pydantic import BaseModel
                from mini_agent.tools.base import Tool

                class NoArgs(BaseModel):
                    pass

                def setup(ctx):
                    ctx.kv_set("version", "two")
                    ctx.register_tool(Tool("reload_tool_v2", "V2", NoArgs, lambda args: {"version": "two"}))
                """
            ),
            encoding="utf-8",
        )

        result = await manager.reload("workspace", "reloadable")

        assert result.ok is True
        assert manager.tools.has_tool("reload_tool_v1") is False
        assert manager.tools.has_tool("reload_tool_v2") is True
        assert manager.kv_get("workspace:reloadable", "torn_down") == "yes"
        assert manager.kv_get("workspace:reloadable", "version") == "two"

    asyncio.run(scenario())


def test_locked_plugin_cannot_be_disabled(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.tools.registry import ToolRegistry

    manager = PluginManager(
        workspace=tmp_path,
        tools=ToolRegistry(),
        builtin_plugins={"core": lambda ctx: None},
        locked_plugins={("builtin", "core")},
    )
    manager.load_all()

    async def scenario():
        result = await manager.disable("builtin", "core")

        assert result.ok is False
        assert result.plugin.enabled is True
        assert result.plugin.loaded is True
        assert "系统插件不可关闭" in result.message

    asyncio.run(scenario())


def test_group_message_plugin_archives_and_reads_current_group(tmp_path):
    from mini_agent.plugins.group_messages import setup
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        manager = PluginManager(
            workspace=tmp_path,
            tools=ToolRegistry(),
            builtin_plugins={"group_messages": setup},
        )
        result = manager.load_all()

        await manager.emit(
            "group_message",
            {
                "group_id": "67890",
                "sender_id": "12345",
                "sender_name": "Alice",
                "text": "hello group",
                "message_id": "101",
                "timestamp": 1710000000,
                "mentioned_bot": False,
            },
        )
        read = await manager.tools.execute(
            "read_group_messages",
            {"limit": 10},
            context={"channel": "qq", "chat_id": "gqq:67890"},
        )

        assert result.loaded == ["group_messages"]
        assert read.success is True
        assert read.content == {
            "group_id": "67890",
            "messages": [
                {
                    "sender_id": "12345",
                    "sender_name": "Alice",
                    "text": "hello group",
                    "message_id": "101",
                    "timestamp": 1710000000,
                    "mentioned_bot": False,
                }
            ],
        }

    asyncio.run(scenario())


def test_group_message_plugin_requires_group_outside_group_context(tmp_path):
    from mini_agent.plugins.group_messages import setup
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        manager = PluginManager(
            workspace=tmp_path,
            tools=ToolRegistry(),
            builtin_plugins={"group_messages": setup},
        )
        manager.load_all()

        result = await manager.tools.execute(
            "read_group_messages",
            {},
            context={"channel": "qq", "chat_id": "12345"},
        )

        assert result.success is False
        assert "group_id" in result.error

    asyncio.run(scenario())


def test_group_message_plugin_keeps_latest_200_and_caps_query_at_100(tmp_path):
    from mini_agent.plugins.group_messages import setup
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        manager = PluginManager(
            workspace=tmp_path,
            tools=ToolRegistry(),
            builtin_plugins={"group_messages": setup},
        )
        manager.load_all()

        for index in range(205):
            await manager.emit(
                "group_message",
                {
                    "group_id": "67890",
                    "sender_id": "12345",
                    "sender_name": "",
                    "text": f"message {index}",
                    "message_id": str(index),
                    "timestamp": index,
                    "mentioned_bot": False,
                },
            )

        result = await manager.tools.execute(
            "read_group_messages",
            {"group_id": "67890", "limit": 500},
        )
        stored = manager.kv_get("group_messages", "group:67890")

        assert len(stored) == 200
        assert stored[0]["text"] == "message 5"
        assert len(result.content["messages"]) == 100
        assert result.content["messages"][0]["text"] == "message 105"
        assert result.content["messages"][-1]["text"] == "message 204"

    asyncio.run(scenario())


def test_xiaohongshu_search_plugin_filters_sorts_and_formats_links(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.plugins.xiaohongshu_search import create_setup
    from mini_agent.tools.registry import ToolRegistry

    async def fake_fetch(args, settings):
        assert settings["endpoint"] == "https://search.example.test/xhs"
        assert settings["api_key"] == "secret"
        assert args.query == "上海 咖啡"
        return [
            {
                "title": "旧的上海咖啡探店",
                "url": "https://www.xiaohongshu.com/explore/old",
                "published_at": "2024-05-01T10:00:00+08:00",
                "content": "安静 适合工作",
            },
            {
                "title": "最新上海咖啡馆",
                "link": "https://www.xiaohongshu.com/explore/new",
                "timestamp": 1714701600,
                "summary": "安静 有插座",
            },
            {
                "title": "广告 上海咖啡",
                "url": "https://www.xiaohongshu.com/explore/ad",
                "published_at": "2025-01-01T10:00:00+08:00",
                "content": "广告 安静",
            },
            {
                "title": "没有链接的上海咖啡",
                "published_at": "2026-01-01T10:00:00+08:00",
                "content": "安静",
            },
        ]

    async def scenario():
        manager = PluginManager(
            workspace=tmp_path,
            tools=ToolRegistry(),
            builtin_plugins={
                "xiaohongshu_search": create_setup(
                    fetcher=fake_fetch,
                    endpoint="https://search.example.test/xhs",
                    api_key="secret",
                )
            },
        )
        manager.load_all()

        result = await manager.tools.execute(
            "search_xiaohongshu_posts",
            {
                "query": "上海 咖啡",
                "require_keywords": ["安静"],
                "exclude_keywords": ["广告"],
                "limit": 10,
            },
        )

        assert result.success is True
        assert [item["title"] for item in result.content["items"]] == [
            "最新上海咖啡馆",
            "旧的上海咖啡探店",
        ]
        assert result.text.splitlines() == [
            "2024-05-03 最新上海咖啡馆 https://www.xiaohongshu.com/explore/new",
            "2024-05-01 旧的上海咖啡探店 https://www.xiaohongshu.com/explore/old",
        ]

    asyncio.run(scenario())


def test_xiaohongshu_search_plugin_can_use_fetcher_without_endpoint(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.plugins.xiaohongshu_search import create_setup
    from mini_agent.tools.registry import ToolRegistry

    async def fake_fetch(args, settings):
        assert settings["endpoint"] == ""
        return [
            {
                "title": "No endpoint fallback",
                "url": "https://www.xiaohongshu.com/explore/fallback",
                "published_at": "2026-06-13",
                "content": args.query,
            }
        ]

    async def scenario():
        manager = PluginManager(
            workspace=tmp_path,
            tools=ToolRegistry(),
            builtin_plugins={
                "xiaohongshu_search": create_setup(fetcher=fake_fetch, endpoint="")
            },
        )
        manager.load_all()

        result = await manager.tools.execute(
            "search_xiaohongshu_posts",
            {"query": "agent remote", "limit": 5},
        )

        assert result.success is True
        assert result.content["items"][0]["url"] == "https://www.xiaohongshu.com/explore/fallback"

    asyncio.run(scenario())


def test_xiaohongshu_search_plugin_calls_http_mcp_with_latest_sort(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.plugins.xiaohongshu_search import create_setup
    from mini_agent.tools.registry import ToolRegistry

    calls = []

    async def fake_transport(endpoint, payload, headers, timeout):
        calls.append(
            {
                "endpoint": endpoint,
                "payload": payload,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '{"items":[{"title":"New role","url":"https://www.xiaohongshu.com/explore/new","published_at":"2026-06-13"}]}',
                    }
                ]
            }
        }

    async def scenario():
        manager = PluginManager(
            workspace=tmp_path,
            tools=ToolRegistry(),
            builtin_plugins={
                "xiaohongshu_search": create_setup(
                    endpoint="http://localhost:18060/mcp",
                    api_key="token",
                    mcp_transport=fake_transport,
                )
            },
        )
        manager.load_all()

        result = await manager.tools.execute(
            "search_xiaohongshu_posts",
            {
                "query": "agent startup remote role",
                "require_keywords": ["role"],
                "publish_time": "一周内",
                "limit": 5,
            },
        )

        assert result.success is True
        assert result.content["items"][0]["title"] == "New role"
        assert [call["payload"]["method"] for call in calls] == [
            "initialize",
            "tools/call",
        ]
        assert calls[1] == {
            "endpoint": "http://localhost:18060/mcp",
            "payload": {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "search_feeds",
                    "arguments": {
                        "keyword": "agent startup remote role",
                        "filters": {
                            "sort_by": "最新",
                            "publish_time": "一周内",
                        },
                    },
                },
            },
            "headers": {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": "Bearer token",
            },
            "timeout": 45,
        }

    asyncio.run(scenario())


def test_xiaohongshu_search_plugin_initializes_streamable_http_mcp_session(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.plugins.xiaohongshu_search import create_setup
    from mini_agent.tools.registry import ToolRegistry

    calls = []

    async def fake_transport(endpoint, payload, headers, timeout):
        calls.append(
            {
                "endpoint": endpoint,
                "payload": payload,
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        if payload["method"] == "initialize":
            return {
                "headers": {"mcp-session-id": "session-123"},
                "body": {
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {"listChanged": True}},
                        "serverInfo": {"name": "xiaohongshu-mcp", "version": "2.0.0"},
                    },
                },
            }
        return {
            "body": {
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": '{"items":[{"title":"New role","url":"https://www.xiaohongshu.com/explore/new","published_at":"2026-06-13"}]}',
                        }
                    ]
                }
            }
        }

    async def scenario():
        manager = PluginManager(
            workspace=tmp_path,
            tools=ToolRegistry(),
            builtin_plugins={
                "xiaohongshu_search": create_setup(
                    endpoint="http://localhost:18060/mcp",
                    api_key="token",
                    mcp_transport=fake_transport,
                )
            },
        )
        manager.load_all()

        result = await manager.tools.execute(
            "search_xiaohongshu_posts",
            {"query": "agent startup remote role", "publish_time": "last week"},
        )

        assert result.success is True
        assert [call["payload"]["method"] for call in calls] == [
            "initialize",
            "tools/call",
        ]
        assert calls[0]["payload"]["params"]["clientInfo"]["name"] == "mini-agent"
        assert calls[1]["headers"]["Mcp-Session-Id"] == "session-123"
        assert calls[1]["payload"]["params"]["arguments"]["filters"] == {
            "sort_by": "最新",
            "publish_time": "一周内",
        }

    asyncio.run(scenario())


def test_xiaohongshu_search_plugin_reports_mcp_connection_failure_actionably(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.plugins.xiaohongshu_search import create_setup
    from mini_agent.tools.registry import ToolRegistry

    async def fake_transport(endpoint, payload, headers, timeout):
        raise RuntimeError("All connection attempts failed")

    async def scenario():
        manager = PluginManager(
            workspace=tmp_path,
            tools=ToolRegistry(),
            builtin_plugins={
                "xiaohongshu_search": create_setup(
                    endpoint="http://localhost:18060/mcp",
                    mcp_transport=fake_transport,
                )
            },
        )
        manager.load_all()

        result = await manager.tools.execute(
            "search_xiaohongshu_posts",
            {"query": "agent startup remote role"},
        )

        assert result.success is False
        assert "xiaohongshu-mcp 连接失败" in result.error
        assert "docker/xiaohongshu-mcp" in result.error

    asyncio.run(scenario())


def test_xiaohongshu_search_plugin_reports_mcp_timeout_actionably(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.plugins.xiaohongshu_search import create_setup
    from mini_agent.tools.registry import ToolRegistry

    class BlankTimeout(Exception):
        def __str__(self):
            return ""

    async def fake_transport(endpoint, payload, headers, timeout):
        if payload["method"] == "initialize":
            return {
                "headers": {"mcp-session-id": "session-123"},
                "body": {"result": {"protocolVersion": "2025-03-26"}},
            }
        raise BlankTimeout()

    async def scenario():
        manager = PluginManager(
            workspace=tmp_path,
            tools=ToolRegistry(),
            builtin_plugins={
                "xiaohongshu_search": create_setup(
                    endpoint="http://localhost:18060/mcp",
                    mcp_transport=fake_transport,
                )
            },
        )
        manager.load_all()

        result = await manager.tools.execute(
            "search_xiaohongshu_posts",
            {"query": "agent startup remote role"},
        )

        assert result.success is False
        assert "xiaohongshu-mcp 请求超时" in result.error
        assert "扫码登录" in result.error

    asyncio.run(scenario())


def test_xiaohongshu_search_plugin_normalizes_mcp_feed_cards_newest_first(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.plugins.xiaohongshu_search import create_setup
    from mini_agent.tools.registry import ToolRegistry

    async def fake_transport(endpoint, payload, headers, timeout):
        return {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": """
                        {
                          "feeds": [
                            {
                              "id": "old-note",
                              "xsecToken": "old-token",
                                "noteCard": {
                                  "displayTitle": "Old agent role",
                                  "desc": "remote startup",
                                  "time": 1780185600000
                                }
                              },
                            {
                              "id": "new-note",
                              "xsec_token": "new-token",
                              "note_card": {
                                "display_title": "New agent role",
                                "desc": "remote startup",
                                "time": 1780272000000
                              }
                            }
                          ]
                        }
                        """,
                    }
                ]
            }
        }

    async def scenario():
        manager = PluginManager(
            workspace=tmp_path,
            tools=ToolRegistry(),
            builtin_plugins={
                "xiaohongshu_search": create_setup(
                    endpoint="http://localhost:18060/mcp",
                    mcp_transport=fake_transport,
                )
            },
        )
        manager.load_all()

        result = await manager.tools.execute(
            "search_xiaohongshu_posts",
            {
                "query": "agent startup remote role",
                "require_keywords": ["remote"],
                "limit": 10,
            },
        )

        assert result.success is True
        assert [item["title"] for item in result.content["items"]] == [
            "New agent role",
            "Old agent role",
        ]
        assert result.content["items"][0]["url"] == (
            "https://www.xiaohongshu.com/explore/new-note?xsec_token=new-token"
        )
        assert result.text.splitlines() == [
            "2026-06-01 New agent role https://www.xiaohongshu.com/explore/new-note?xsec_token=new-token",
            "2026-05-31 Old agent role https://www.xiaohongshu.com/explore/old-note?xsec_token=old-token",
        ]

    asyncio.run(scenario())


def test_xiaohongshu_public_search_parser_extracts_links_dates_and_text():
    from mini_agent.plugins.xiaohongshu_search import (
        SearchXiaohongshuPostsArgs,
        _extract_public_search_results,
        _select_items,
    )

    html = """
    <li class="b_algo">
      <h2><a href="https://www.xiaohongshu.com/explore/old-note">Old agent role</a></h2>
      <p>2026-05-01 Agent startup remote role.</p>
    </li>
    <li class="b_algo">
      <h2><a href="https://www.example.com/not-xhs">Ignore me</a></h2>
      <p>2026-06-12 Agent startup remote role.</p>
    </li>
    <li class="b_algo">
      <h2><a href="https://www.xiaohongshu.com/explore/new-note?xsec_token=abc">New agent role</a></h2>
      <p>2026年6月12日 Agent startup remote role.</p>
    </li>
    """

    raw_items = _extract_public_search_results(html)
    items = _select_items(
        raw_items,
        SearchXiaohongshuPostsArgs(query="agent remote", limit=10),
    )

    assert [item["title"] for item in items] == ["New agent role", "Old agent role"]
    assert items[0]["published_at"] == "2026-06-12"
    assert items[0]["url"] == "https://www.xiaohongshu.com/explore/new-note?xsec_token=abc"

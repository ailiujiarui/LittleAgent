import asyncio
import textwrap


def _write_plugin(root, name, source):
    plugin_dir = root / "plugins" / name
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.py").write_text(textwrap.dedent(source), encoding="utf-8")
    return plugin_dir


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
        result = manager.load_all()
        executed = await registry.execute("plugin_echo", {"text": "hello"})

        assert result.loaded == ["echo_plugin"]
        assert result.failed == {}
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
        manager.load_all()

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

    manager = PluginManager(workspace=tmp_path, tools=ToolRegistry())
    result = manager.load_all()

    assert result.loaded == ["good"]
    assert "bad" in result.failed
    assert manager.tools.has_tool("good_tool") is True


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


def test_xiaohongshu_search_plugin_requires_endpoint(tmp_path):
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.plugins.xiaohongshu_search import create_setup
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        manager = PluginManager(
            workspace=tmp_path,
            tools=ToolRegistry(),
            builtin_plugins={"xiaohongshu_search": create_setup(endpoint="")},
        )
        manager.load_all()

        result = await manager.tools.execute(
            "search_xiaohongshu_posts",
            {"query": "上海 咖啡"},
        )

        assert result.success is False
        assert "XHS_SEARCH_ENDPOINT" in result.error

    asyncio.run(scenario())

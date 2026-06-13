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

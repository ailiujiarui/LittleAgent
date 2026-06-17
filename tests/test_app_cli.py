from typer.testing import CliRunner


def test_cli_exposes_expected_commands():
    from mini_agent.__main__ import app

    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ["init", "run", "dashboard", "qq-check", "mcp-list"]:
        assert command in result.output


def test_dashboard_cli_exposes_access_token_option():
    from mini_agent.__main__ import app

    result = CliRunner().invoke(app, ["dashboard", "--help"])

    assert result.exit_code == 0
    assert "--access-token" in result.output


def test_dashboard_cli_passes_access_token(monkeypatch, tmp_path):
    from mini_agent.__main__ import app

    captured = {}

    def fake_create_dashboard_app(workspace, access_token=None):
        captured["workspace"] = workspace
        captured["access_token"] = access_token
        return object()

    def fake_uvicorn_run(app_instance, host, port):
        captured["app"] = app_instance
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("mini_agent.__main__.create_dashboard_app", fake_create_dashboard_app)
    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)

    result = CliRunner().invoke(
        app,
        [
            "dashboard",
            "--workspace",
            str(tmp_path),
            "--host",
            "127.0.0.1",
            "--port",
            "9898",
            "--access-token",
            "secret",
        ],
    )

    assert result.exit_code == 0
    assert captured["workspace"] == tmp_path
    assert captured["access_token"] == "secret"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9898


def test_cli_init_creates_workspace(tmp_path):
    from mini_agent.__main__ import app

    workspace = tmp_path / "workspace"
    result = CliRunner().invoke(app, ["init", "--workspace", str(workspace)])

    assert result.exit_code == 0
    assert (workspace / "memory" / "MEMORY.md").exists()
    assert (workspace / "mcp_servers.json").exists()


def test_app_runtime_dry_run_builds_services(tmp_path):
    from mini_agent.app import AppRuntime
    from mini_agent.config import AppConfig, XiaohongshuConfig

    runtime = AppRuntime(
        AppConfig(
            workspace=tmp_path,
            xiaohongshu=XiaohongshuConfig(
                search_endpoint="https://search.example.test/xhs",
                search_api_key="secret",
            ),
        )
    )

    summary = runtime.dry_run()

    assert summary["workspace"] == str(tmp_path)
    assert "get_time" in summary["tools"]
    assert "message_push" in summary["tools"]
    assert "read_group_messages" in summary["tools"]
    assert "search_xiaohongshu_posts" in summary["tools"]
    assert summary["plugins"]["loaded"] == ["group_messages", "xiaohongshu_search"]
    assert summary["mcp"]["enabled"] is True
    assert summary["proactive"]["enabled"] is False
    assert summary["drift"]["enabled"] is False
    assert summary["dashboard"]["enabled"] is False
    assert (tmp_path / "agent.db").exists()


def test_app_runtime_start_runtime_services_connects_mcp(tmp_path):
    from mini_agent.app import AppRuntime
    from mini_agent.config import AppConfig

    async def scenario():
        runtime = AppRuntime(AppConfig(workspace=tmp_path))
        runtime.build_services()
        calls = []

        class FakeMcp:
            failed = {}
            server_tools = {"demo": ["echo"]}

            async def connect_all(self):
                calls.append("connect_all")

        runtime.mcp = FakeMcp()

        summary = await runtime.start_runtime_services(start_onebot=False)

        assert calls == ["connect_all"]
        assert summary["mcp"] == {"connected": {"demo": ["echo"]}, "failed": {}}

    import asyncio

    asyncio.run(scenario())


def test_app_runtime_builds_proactive_and_drift_when_enabled(tmp_path):
    from mini_agent.app import AppRuntime
    from mini_agent.config import AppConfig, DriftConfig, ProactiveConfig, ProactiveSourceConfig

    runtime = AppRuntime(
        AppConfig(
            workspace=tmp_path,
            proactive=ProactiveConfig(
                enabled=True,
                target_chat_id="123",
                sources=[
                    ProactiveSourceConfig(
                        type="rss",
                        name="agent-news",
                        url="https://example.test/feed.xml",
                    ),
                    ProactiveSourceConfig(
                        type="http_json",
                        name="alerts",
                        url="https://example.test/alerts.json",
                    ),
                ],
            ),
            drift=DriftConfig(enabled=True),
        )
    )

    summary = runtime.dry_run()

    assert summary["proactive"]["enabled"] is True
    assert summary["proactive"]["sources"] == ["agent-news", "alerts"]
    assert summary["drift"]["enabled"] is True
    assert runtime.proactive_loop is not None
    assert [source.name for source in runtime.proactive_loop.sources] == [
        "agent-news",
        "alerts",
    ]
    assert runtime.drift_loop is not None


def test_app_runtime_rejects_unknown_proactive_source_type(tmp_path):
    import pytest

    from mini_agent.app import AppRuntime
    from mini_agent.config import AppConfig, ProactiveConfig, ProactiveSourceConfig

    runtime = AppRuntime(
        AppConfig(
            workspace=tmp_path,
            proactive=ProactiveConfig(
                enabled=True,
                target_chat_id="123",
                sources=[
                    ProactiveSourceConfig(
                        type="unsupported",
                        name="bad",
                        url="https://example.test/bad",
                    )
                ],
            ),
        )
    )

    with pytest.raises(ValueError, match="unsupported proactive source type"):
        runtime.dry_run()


def test_app_runtime_starts_background_proactive_task(tmp_path):
    from mini_agent.app import AppRuntime
    from mini_agent.config import AppConfig, ProactiveConfig

    async def scenario():
        runtime = AppRuntime(
            AppConfig(
                workspace=tmp_path,
                proactive=ProactiveConfig(
                    enabled=True,
                    target_chat_id="123",
                    interval_seconds=60,
                ),
            )
        )
        runtime.build_services()
        await runtime.start_runtime_services(start_onebot=False)

        assert len(runtime.background_tasks) == 1

        await runtime.stop_runtime_services()

    import asyncio

    asyncio.run(scenario())


def test_app_runtime_starts_dashboard_when_enabled(monkeypatch, tmp_path):
    from mini_agent.app import AppRuntime
    from mini_agent.config import AppConfig, DashboardConfig

    async def scenario():
        runtime = AppRuntime(
            AppConfig(
                workspace=tmp_path,
                dashboard=DashboardConfig(enabled=True, host="127.0.0.1", port=9898),
            )
        )
        runtime.build_services()
        calls = []

        async def fake_start_dashboard():
            calls.append((runtime.config.dashboard.host, runtime.config.dashboard.port))
            return {"running": True, "url": "http://127.0.0.1:9898"}

        monkeypatch.setattr(runtime, "_start_dashboard", fake_start_dashboard)

        summary = await runtime.start_runtime_services(start_onebot=False)

        assert calls == [("127.0.0.1", 9898)]
        assert summary["dashboard"] == {
            "running": True,
            "url": "http://127.0.0.1:9898",
        }

        await runtime.stop_runtime_services()

    import asyncio

    asyncio.run(scenario())


def test_app_runtime_passes_dashboard_access_token(monkeypatch, tmp_path):
    from mini_agent.app import AppRuntime
    from mini_agent.config import AppConfig, DashboardConfig, MCPConfig

    async def scenario():
        captured = {}

        def fake_create_dashboard_app(workspace, status=None, access_token=None):
            captured["workspace"] = workspace
            captured["status"] = status
            captured["access_token"] = access_token
            return object()

        class FakeConfig:
            def __init__(self, app, host, port, log_level):
                captured["host"] = host
                captured["port"] = port
                captured["log_level"] = log_level

        class FakeServer:
            def __init__(self, config):
                self.config = config
                self.started = True
                self.should_exit = False

            async def serve(self):
                return None

        monkeypatch.setattr("mini_agent.app.create_dashboard_app", fake_create_dashboard_app)
        monkeypatch.setattr("uvicorn.Config", FakeConfig)
        monkeypatch.setattr("uvicorn.Server", FakeServer)

        runtime = AppRuntime(
            AppConfig(
                workspace=tmp_path,
                mcp=MCPConfig(enabled=False),
                dashboard=DashboardConfig(
                    enabled=True,
                    host="127.0.0.1",
                    port=9898,
                    access_token="secret",
                ),
            )
        )
        runtime.build_services()

        await runtime.start_runtime_services(start_onebot=False)
        await runtime.stop_runtime_services()

        assert captured["access_token"] == "secret"
        assert captured["host"] == "127.0.0.1"
        assert captured["port"] == 9898

    import asyncio

    asyncio.run(scenario())


def test_app_runtime_injects_xiaohongshu_config_into_plugin(tmp_path):
    from mini_agent.app import AppRuntime
    from mini_agent.config import AppConfig, XiaohongshuConfig

    async def scenario():
        runtime = AppRuntime(
            AppConfig(
                workspace=tmp_path,
                xiaohongshu=XiaohongshuConfig(
                    search_endpoint="https://search.example.test/xhs",
                    search_api_key="secret",
                ),
            )
        )
        runtime.build_services()

        tool = runtime.tools.get_tool("search_xiaohongshu_posts")

        assert tool is not None
        assert "https://search.example.test/xhs" in tool.description

    import asyncio

    asyncio.run(scenario())


def test_app_runtime_startup_lines_show_listening_details(tmp_path):
    from mini_agent.app import AppRuntime
    from mini_agent.config import AppConfig, OneBotConfig

    runtime = AppRuntime(
        AppConfig(
            workspace=tmp_path,
            onebot=OneBotConfig(bot_uin="123456789", port=8765),
        )
    )

    lines = runtime.startup_lines()

    assert "workspace: " + str(tmp_path) in lines
    assert "OneBot listening: ws://127.0.0.1:8765/onebot/v11/ws" in lines
    assert "bot_uin: 123456789" in lines


def test_app_runtime_passes_onebot_path_and_access_token(tmp_path):
    from mini_agent.app import AppRuntime
    from mini_agent.config import AppConfig, OneBotConfig

    runtime = AppRuntime(
        AppConfig(
            workspace=tmp_path,
            onebot=OneBotConfig(
                path="/onebot/custom/ws",
                access_token="secret",
            ),
        )
    )

    runtime.build_services()

    assert runtime.onebot.path == "/onebot/custom/ws"
    assert runtime.onebot.access_token == "secret"


def test_app_runtime_default_logger_flushes(monkeypatch, tmp_path):
    from mini_agent.app import AppRuntime
    from mini_agent.config import AppConfig

    calls = []

    def fake_print(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("builtins.print", fake_print)
    runtime = AppRuntime(AppConfig(workspace=tmp_path))

    runtime.logger("ready")

    assert calls == [(("ready",), {"flush": True})]


def test_app_runtime_archives_group_message_without_reply_trigger(tmp_path):
    from mini_agent.app import AppRuntime
    from mini_agent.config import AppConfig, OneBotConfig

    async def scenario():
        runtime = AppRuntime(
            AppConfig(
                workspace=tmp_path,
                onebot=OneBotConfig(
                    bot_uin="10000",
                    groups={"67890": {"allow_from": [], "require_at": True}},
                ),
            )
        )
        runtime.build_services()

        result = await runtime.onebot.handle_event(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 67890,
                "user_id": 12345,
                "message": "quiet group context",
            }
        )
        read = await runtime.tools.execute(
            "read_group_messages",
            {"group_id": "67890"},
        )

        assert result is None
        assert runtime.bus._queue().empty()
        assert read.success is True
        assert read.content["messages"][0]["text"] == "quiet group context"

    import asyncio

    asyncio.run(scenario())


def test_cli_run_dry_run(tmp_path):
    from mini_agent.__main__ import app

    result = CliRunner().invoke(
        app,
        ["run", "--dry-run", "--workspace", str(tmp_path / "workspace")],
    )

    assert result.exit_code == 0
    assert "dry-run ok" in result.output.lower()


def test_cli_run_reports_onebot_port_in_use(monkeypatch, tmp_path):
    from mini_agent.__main__ import app
    from mini_agent.app import AppRuntime

    async def raise_port_in_use(self):
        raise OSError(
            10048,
            "error while attempting to bind on address "
            "('127.0.0.1', 8765): only one usage allowed",
        )

    monkeypatch.setattr(AppRuntime, "run_forever", raise_port_in_use)

    result = CliRunner().invoke(
        app,
        ["run", "--workspace", str(tmp_path / "workspace")],
    )

    assert result.exit_code == 1
    assert "OneBot port is already in use:" in result.output
    assert ":8765" in result.output

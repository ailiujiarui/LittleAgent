import textwrap

from fastapi.testclient import TestClient


def _write_plugin(root, name, source):
    plugin_dir = root / "plugins" / name
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.py").write_text(textwrap.dedent(source), encoding="utf-8")
    return plugin_dir


def test_dashboard_lists_sessions_and_messages(tmp_path):
    import sqlite3

    from mini_agent.dashboard.server import create_dashboard_app
    from mini_agent.db.migrations import apply_migrations

    db_path = tmp_path / "agent.db"
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            insert into sessions (id, channel, chat_id, created_at, updated_at)
            values ('qq:12345', 'qq', '12345', '2026-06-15 10:00:00', '2026-06-15 10:01:00')
            """
        )
        conn.execute(
            """
            insert into messages (session_id, role, content, created_at)
            values ('qq:12345', 'user', 'hello', '2026-06-15 10:00:10')
            """
        )
        conn.execute(
            """
            insert into messages (session_id, role, content, created_at)
            values ('qq:12345', 'assistant', 'pong', '2026-06-15 10:00:20')
            """
        )
        conn.commit()

    client = TestClient(create_dashboard_app(workspace=tmp_path))

    sessions = client.get("/api/sessions").json()["sessions"]
    detail = client.get("/api/sessions/qq:12345").json()

    assert sessions == [
        {
            "id": "qq:12345",
            "channel": "qq",
            "chat_id": "12345",
            "created_at": "2026-06-15 10:00:00",
            "updated_at": "2026-06-15 10:01:00",
            "message_count": 2,
        }
    ]
    assert detail["session"]["id"] == "qq:12345"
    assert detail["messages"] == [
        {
            "id": 1,
            "role": "user",
            "content": "hello",
            "created_at": "2026-06-15 10:00:10",
        },
        {
            "id": 2,
            "role": "assistant",
            "content": "pong",
            "created_at": "2026-06-15 10:00:20",
        },
    ]


def test_dashboard_returns_404_for_missing_session(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app

    client = TestClient(create_dashboard_app(workspace=tmp_path))

    response = client.get("/api/sessions/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "会话不存在"


def test_dashboard_lists_events_proactive_items_and_drift_runs(tmp_path):
    import sqlite3

    from mini_agent.dashboard.server import create_dashboard_app
    from mini_agent.db.migrations import apply_migrations

    db_path = tmp_path / "agent.db"
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            insert into runtime_events (event_type, payload_json, created_at)
            values ('startup', '{"ok": true}', '2026-06-15 09:00:00')
            """
        )
        conn.execute(
            """
            insert into tool_events (
                session_id, tool_name, arguments_json, result_json, created_at
            )
            values (
                'qq:12345', 'get_time', '{"timezone": "Asia/Shanghai"}',
                '{"success": true}', '2026-06-15 09:01:00'
            )
            """
        )
        conn.execute(
            """
            insert into proactive_items (
                source, item_key, title, url, judged_at, pushed_at
            )
            values (
                'rss', 'item-1', 'Important update', 'https://example.test/item-1',
                '2026-06-15 09:02:00', '2026-06-15 09:03:00'
            )
            """
        )
        conn.execute(
            """
            insert into drift_runs (started_at, finished_at, status, summary)
            values (
                '2026-06-15 09:04:00', '2026-06-15 09:05:00',
                'finished', 'daily check'
            )
            """
        )
        conn.commit()

    client = TestClient(create_dashboard_app(workspace=tmp_path))

    events = client.get("/api/events").json()["events"]
    proactive = client.get("/api/proactive").json()["items"]
    drift = client.get("/api/drift").json()["runs"]

    assert events[0]["kind"] == "tool"
    assert events[0]["tool_name"] == "get_time"
    assert events[0]["arguments"] == {"timezone": "Asia/Shanghai"}
    assert events[0]["result"] == {"success": True}
    assert events[1]["kind"] == "runtime"
    assert events[1]["event_type"] == "startup"
    assert events[1]["payload"] == {"ok": True}
    assert proactive == [
        {
            "id": 1,
            "source": "rss",
            "item_key": "item-1",
            "title": "Important update",
            "url": "https://example.test/item-1",
            "judged_at": "2026-06-15 09:02:00",
            "pushed_at": "2026-06-15 09:03:00",
        }
    ]
    assert drift == [
        {
            "id": 1,
            "started_at": "2026-06-15 09:04:00",
            "finished_at": "2026-06-15 09:05:00",
            "status": "finished",
            "summary": "daily check",
        }
    ]


def test_dashboard_index_returns_chinese_missing_vue_build_fallback(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app

    client = TestClient(
        create_dashboard_app(workspace=tmp_path, static_dir=tmp_path / "missing-dist")
    )

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "小助手控制台" in html
    assert "控制台前端尚未构建" in html
    assert "dashboard-ui" in html
    assert "npm run build" in html
    assert "Mini Agent Dashboard" not in html


def test_dashboard_serves_vue_dist_index_when_built(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app

    dist = tmp_path / "dashboard-ui" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html><body><div id="app">Vue 控制台</div></body></html>',
        encoding="utf-8",
    )

    client = TestClient(create_dashboard_app(workspace=tmp_path, static_dir=dist))

    response = client.get("/")

    assert response.status_code == 200
    assert "Vue 控制台" in response.text


def test_dashboard_serves_vue_dist_assets_when_built(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app

    dist = tmp_path / "dashboard-ui" / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><script type="module" src="/assets/app.js"></script>',
        encoding="utf-8",
    )
    (assets / "app.js").write_text("console.log('控制台资源');", encoding="utf-8")

    client = TestClient(create_dashboard_app(workspace=tmp_path, static_dir=dist))

    response = client.get("/assets/app.js")

    assert response.status_code == 200
    assert "控制台资源" in response.text


def test_dashboard_plugin_api_lists_standalone_plugins_and_requires_auth(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app

    _write_plugin(
        tmp_path,
        "demo",
        """
        def setup(ctx):
            (ctx.workspace / "setup-ran.txt").write_text("yes", encoding="utf-8")
        """,
    )

    protected = TestClient(
        create_dashboard_app(workspace=tmp_path, access_token="secret")
    )
    assert protected.get("/api/plugins").status_code == 401
    assert (
        protected.get(
            "/api/plugins",
            headers={"Authorization": "Bearer secret"},
        ).status_code
        == 200
    )

    client = TestClient(create_dashboard_app(workspace=tmp_path))
    payload = client.get("/api/plugins").json()
    plugins = {plugin["id"]: plugin for plugin in payload["plugins"]}

    assert payload["mode"] == "standalone"
    assert "builtin:group_messages" in plugins
    assert "builtin:xiaohongshu_search" in plugins
    assert plugins["workspace:demo"]["enabled"] is False
    assert plugins["workspace:demo"]["loaded"] is False
    assert not (tmp_path / "setup-ran.txt").exists()


def test_dashboard_plugin_api_standalone_enable_persists_for_next_start(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app
    from mini_agent.plugins.state import PluginStateStore

    _write_plugin(
        tmp_path,
        "demo",
        """
        def setup(ctx):
            (ctx.workspace / "setup-ran.txt").write_text("yes", encoding="utf-8")
        """,
    )

    client = TestClient(create_dashboard_app(workspace=tmp_path))

    response = client.post("/api/plugins/workspace/demo/enable")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["requires_restart"] is True
    assert "下次启动后生效" in payload["message"]
    assert payload["plugin"]["enabled"] is True
    state = PluginStateStore(tmp_path / "agent.db").get("workspace", "demo")
    assert state.enabled is True
    assert not (tmp_path / "setup-ran.txt").exists()


def test_dashboard_plugin_api_runtime_enable_disable_reload_hotplugs(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app
    from mini_agent.plugins.manager import PluginManager
    from mini_agent.tools.registry import ToolRegistry

    plugin_dir = _write_plugin(
        tmp_path,
        "demo",
        """
        from pydantic import BaseModel
        from mini_agent.tools.base import Tool

        class NoArgs(BaseModel):
            pass

        def setup(ctx):
            ctx.kv_set("version", "one")
            ctx.register_tool(
                Tool("dashboard_demo_v1", "Demo v1", NoArgs, lambda args: {"version": "one"})
            )

        def teardown(ctx):
            ctx.kv_set("torn_down", "yes")
        """,
    )
    registry = ToolRegistry()
    manager = PluginManager(workspace=tmp_path, tools=registry)
    client = TestClient(create_dashboard_app(workspace=tmp_path, plugin_manager=manager))

    listed = client.get("/api/plugins").json()
    assert listed["mode"] == "runtime"

    enabled = client.post("/api/plugins/workspace/demo/enable").json()
    assert enabled["ok"] is True
    assert enabled["requires_restart"] is False
    assert registry.has_tool("dashboard_demo_v1") is True

    disabled = client.post("/api/plugins/workspace/demo/disable").json()
    assert disabled["ok"] is True
    assert disabled["plugin"]["enabled"] is False
    assert registry.has_tool("dashboard_demo_v1") is False

    client.post("/api/plugins/workspace/demo/enable")
    (plugin_dir / "plugin.py").write_text(
        textwrap.dedent(
            """
            from pydantic import BaseModel
            from mini_agent.tools.base import Tool

            class NoArgs(BaseModel):
                pass

            def setup(ctx):
                ctx.kv_set("version", "two")
                ctx.register_tool(
                    Tool("dashboard_demo_v2", "Demo v2", NoArgs, lambda args: {"version": "two"})
                )
            """
        ),
        encoding="utf-8",
    )

    reloaded = client.post("/api/plugins/workspace/demo/reload").json()

    assert reloaded["ok"] is True
    assert registry.has_tool("dashboard_demo_v1") is False
    assert registry.has_tool("dashboard_demo_v2") is True
    assert manager.kv_get("workspace:demo", "torn_down") == "yes"
    assert manager.kv_get("workspace:demo", "version") == "two"


def test_dashboard_token_protects_api_when_configured(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app

    client = TestClient(create_dashboard_app(workspace=tmp_path, access_token="secret"))

    unauthorized = client.get("/api/status")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["detail"] == "未授权"
    assert client.get("/api/status?token=wrong").status_code == 401
    assert client.get("/api/status?token=secret").status_code == 401
    assert (
        client.get(
            "/api/status",
            headers={"Authorization": "Bearer secret"},
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/status",
            headers={"Authorization": "bearer secret"},
        ).status_code
        == 200
    )


def test_dashboard_login_sets_http_only_session_cookie(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app

    client = TestClient(create_dashboard_app(workspace=tmp_path, access_token="secret"))

    bad_login = client.post("/api/login", json={"token": "wrong"})
    assert bad_login.status_code == 401
    assert bad_login.json()["detail"] == "访问令牌不正确"

    good_login = client.post("/api/login", json={"token": "secret"})

    assert good_login.status_code == 200
    assert good_login.json() == {"ok": True}
    assert "dashboard_session=" in good_login.headers["set-cookie"]
    assert "HttpOnly" in good_login.headers["set-cookie"]
    assert client.get("/api/status").status_code == 200


def test_dashboard_login_page_and_authenticated_index_are_chinese(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app

    client = TestClient(create_dashboard_app(workspace=tmp_path, access_token="secret"))

    login = client.get("/")
    tokenized = client.get("/?token=secret")

    assert login.status_code == 200
    assert "访问令牌" in login.text
    assert "进入控制台" in login.text
    assert "访问令牌不正确" in login.text
    assert "Login" not in login.text
    assert "secret" not in login.text
    assert tokenized.status_code == 200
    assert "访问令牌" in tokenized.text
    assert "小助手控制台" in tokenized.text

    client.post("/api/login", json={"token": "secret"})
    dashboard = client.get("/")

    assert dashboard.status_code == 200
    assert "小助手控制台" in dashboard.text
    assert "window.__DASHBOARD_TOKEN__" not in dashboard.text
    assert "secret" not in dashboard.text
    assert "API" not in dashboard.text


def test_dashboard_status_endpoint(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app

    client = TestClient(create_dashboard_app(workspace=tmp_path, status={"running": True}))

    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json()["running"] is True
    assert response.json()["workspace"] == str(tmp_path)


def test_dashboard_memory_file_whitelist_read_write_and_backup(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app
    from mini_agent.memory.store import MemoryStore

    store = MemoryStore(tmp_path)
    (store.memory_dir / "MEMORY.md").write_text("old", encoding="utf-8")
    client = TestClient(create_dashboard_app(workspace=tmp_path))

    read_response = client.get("/api/memory/files/MEMORY.md")
    write_response = client.post(
        "/api/memory/files/MEMORY.md",
        json={"content": "new"},
    )

    backups = list((tmp_path / "backups" / "memory").glob("MEMORY.md.*.bak"))
    assert read_response.json()["content"] == "old"
    assert write_response.status_code == 200
    assert (store.memory_dir / "MEMORY.md").read_text(encoding="utf-8") == "new"
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old"


def test_dashboard_rejects_path_traversal(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app

    client = TestClient(create_dashboard_app(workspace=tmp_path))

    response = client.get("/api/memory/files/..%2Fconfig.toml")

    assert response.status_code == 400
    assert response.json()["detail"] == "不支持的记忆文件"

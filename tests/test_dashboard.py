from fastapi.testclient import TestClient


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


def test_dashboard_index_renders_operational_ui(tmp_path):
    from mini_agent.dashboard.server import create_dashboard_app

    client = TestClient(create_dashboard_app(workspace=tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "Mini Agent Dashboard" in html
    assert 'id="runtime-status"' in html
    assert 'id="workspace-path"' in html
    assert 'id="memory-files"' in html
    assert 'id="memory-editor"' in html
    assert 'id="session-list"' in html
    assert 'id="event-list"' in html
    assert 'id="proactive-list"' in html
    assert 'id="drift-list"' in html
    assert 'fetch("/api/status")' in html
    assert 'fetch("/api/memory/files")' in html
    assert 'fetch("/api/sessions")' in html
    assert 'fetch("/api/events")' in html
    assert 'fetch("/api/proactive")' in html
    assert 'fetch("/api/drift")' in html
    assert len(html) > 5000


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

from fastapi.testclient import TestClient


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

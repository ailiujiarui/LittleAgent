import sqlite3


def test_load_config_defaults_to_deepseek_openai_compatible(tmp_path, monkeypatch):
    from mini_agent.config import load_config

    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.llm.base_url == "https://api.deepseek.com"
    assert config.llm.model == "deepseek-v4-flash"
    assert config.xiaohongshu.search_endpoint == "http://localhost:18060/mcp"


def test_load_config_expands_env_and_defaults(tmp_path, monkeypatch):
    from mini_agent.config import load_config

    monkeypatch.setenv("AGENT_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setenv("TEST_LLM_KEY", "sk-test")
    monkeypatch.setenv("TEST_XHS_KEY", "xhs-secret")
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
workspace = "${AGENT_WORKSPACE}"

[llm]
base_url = "https://llm.example.test/v1"
api_key = "${TEST_LLM_KEY}"
model = "test-model"

[xiaohongshu]
search_endpoint = "https://search.example.test/xhs"
search_api_key = "${TEST_XHS_KEY}"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.workspace == tmp_path / "workspace"
    assert config.llm.api_key == "sk-test"
    assert config.llm.model == "test-model"
    assert config.onebot.host == "127.0.0.1"
    assert config.onebot.port == 8765
    assert config.proactive.enabled is False
    assert config.xiaohongshu.search_endpoint == "https://search.example.test/xhs"
    assert config.xiaohongshu.search_api_key == "xhs-secret"


def test_init_workspace_creates_expected_files_without_overwriting(tmp_path):
    from mini_agent.bootstrap import init_workspace

    workspace = tmp_path / "workspace"
    init_workspace(workspace)

    expected_files = [
        workspace / "memory" / "SELF.md",
        workspace / "memory" / "MEMORY.md",
        workspace / "memory" / "RECENT_CONTEXT.md",
        workspace / "memory" / "HISTORY.md",
        workspace / "memory" / "PENDING.md",
        workspace / "mcp_servers.json",
    ]
    for path in expected_files:
        assert path.exists(), path

    self_file = workspace / "memory" / "SELF.md"
    self_file.write_text("custom identity", encoding="utf-8")
    init_workspace(workspace)

    assert self_file.read_text(encoding="utf-8") == "custom identity"


def test_apply_migrations_is_idempotent(tmp_path):
    from mini_agent.db.migrations import apply_migrations

    db_path = tmp_path / "workspace" / "agent.db"
    db_path.parent.mkdir()

    apply_migrations(db_path)
    apply_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        migrations = conn.execute(
            "select version from schema_migrations order by version"
        ).fetchall()
        tables = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }

    assert migrations == [("001_init",)]
    assert {
        "sessions",
        "messages",
        "tool_events",
        "runtime_events",
        "memory_items",
        "proactive_items",
        "drift_runs",
        "plugin_kv",
    }.issubset(tables)

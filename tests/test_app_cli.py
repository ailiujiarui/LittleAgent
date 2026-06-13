from typer.testing import CliRunner


def test_cli_exposes_expected_commands():
    from mini_agent.__main__ import app

    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ["init", "run", "dashboard", "qq-check", "mcp-list"]:
        assert command in result.output


def test_cli_init_creates_workspace(tmp_path):
    from mini_agent.__main__ import app

    workspace = tmp_path / "workspace"
    result = CliRunner().invoke(app, ["init", "--workspace", str(workspace)])

    assert result.exit_code == 0
    assert (workspace / "memory" / "MEMORY.md").exists()
    assert (workspace / "mcp_servers.json").exists()


def test_app_runtime_dry_run_builds_services(tmp_path):
    from mini_agent.app import AppRuntime
    from mini_agent.config import AppConfig

    runtime = AppRuntime(AppConfig(workspace=tmp_path))

    summary = runtime.dry_run()

    assert summary["workspace"] == str(tmp_path)
    assert "get_time" in summary["tools"]
    assert "message_push" in summary["tools"]
    assert (tmp_path / "agent.db").exists()


def test_cli_run_dry_run(tmp_path):
    from mini_agent.__main__ import app

    result = CliRunner().invoke(
        app,
        ["run", "--dry-run", "--workspace", str(tmp_path / "workspace")],
    )

    assert result.exit_code == 0
    assert "dry-run ok" in result.output.lower()

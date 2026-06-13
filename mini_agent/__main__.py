from pathlib import Path
import asyncio

import typer

from mini_agent.app import AppRuntime
from mini_agent.bootstrap import init_workspace
from mini_agent.config import AppConfig, load_config
from mini_agent.dashboard.server import create_dashboard_app
from mini_agent.mcp.registry import McpRegistry
from mini_agent.tools.registry import ToolRegistry

app = typer.Typer(no_args_is_help=True)


@app.command()
def init(workspace: Path = typer.Option(Path("workspace"), "--workspace")) -> None:
    init_workspace(workspace)
    typer.echo(f"initialized workspace: {workspace}")


@app.command()
def run(
    workspace: Path = typer.Option(Path("workspace"), "--workspace"),
    config: Path = typer.Option(Path("config.toml"), "--config"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    app_config = load_config(config)
    app_config.workspace = workspace
    runtime = AppRuntime(app_config)
    if dry_run:
        summary = runtime.dry_run()
        typer.echo(f"dry-run ok: {summary['workspace']}")
        typer.echo("tools: " + ", ".join(summary["tools"]))
        return
    asyncio.run(runtime.run_forever())


@app.command()
def dashboard(
    workspace: Path = typer.Option(Path("workspace"), "--workspace"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port"),
) -> None:
    import uvicorn

    uvicorn.run(create_dashboard_app(workspace), host=host, port=port)


@app.command("qq-check")
def qq_check(
    config: Path = typer.Option(Path("config.toml"), "--config"),
) -> None:
    app_config = load_config(config)
    typer.echo(
        f"OneBot reverse WebSocket: ws://{app_config.onebot.host}:"
        f"{app_config.onebot.port}{app_config.onebot.path}"
    )
    typer.echo(f"bot_uin: {app_config.onebot.bot_uin}")


@app.command("mcp-list")
def mcp_list(workspace: Path = typer.Option(Path("workspace"), "--workspace")) -> None:
    async def scenario():
        tools = ToolRegistry()
        registry = McpRegistry(workspace / "mcp_servers.json", tools)
        await registry.connect_all()
        result = await tools.execute("mcp_list", {})
        await registry.close_all()
        return result.content["servers"], registry.failed

    servers, failed = asyncio.run(scenario())
    typer.echo(f"servers: {servers}")
    if failed:
        typer.echo(f"failed: {failed}")


if __name__ == "__main__":
    app()

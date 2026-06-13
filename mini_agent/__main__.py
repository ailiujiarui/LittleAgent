from pathlib import Path

import typer

from mini_agent.bootstrap import init_workspace

app = typer.Typer(no_args_is_help=True)


@app.command()
def init(workspace: Path = typer.Option(Path("workspace"), "--workspace")) -> None:
    init_workspace(workspace)
    typer.echo(f"initialized workspace: {workspace}")


if __name__ == "__main__":
    app()

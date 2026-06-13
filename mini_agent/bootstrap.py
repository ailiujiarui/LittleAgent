from pathlib import Path


_MEMORY_FILES = {
    "SELF.md": "# Self\n\n",
    "MEMORY.md": "# Memory\n\n",
    "RECENT_CONTEXT.md": "# Recent Context\n\n",
    "HISTORY.md": "# History\n\n",
    "PENDING.md": "# Pending\n\n",
}


def init_workspace(workspace: Path) -> None:
    workspace = Path(workspace)
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in _MEMORY_FILES.items():
        _write_once(memory_dir / filename, content)

    _write_once(workspace / "mcp_servers.json", "{}\n")
    _write_once(workspace / "PROACTIVE_CONTEXT.md", "# Proactive Context\n\n")
    (workspace / "drift" / "skills").mkdir(parents=True, exist_ok=True)


def _write_once(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

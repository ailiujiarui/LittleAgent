from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from mini_agent.memory.store import WRITABLE_MEMORY_FILES, MemoryStore


class SaveMemoryRequest(BaseModel):
    content: str


def create_dashboard_app(
    workspace: Path,
    status: Optional[Dict[str, object]] = None,
) -> FastAPI:
    workspace = Path(workspace)
    memory = MemoryStore(workspace)
    runtime_status = {"running": False, **(status or {})}

    app = FastAPI(title="Mini Agent Dashboard")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return "<html><body><h1>Mini Agent Dashboard</h1></body></html>"

    @app.get("/api/status")
    def get_status():
        return {"workspace": str(workspace), **runtime_status}

    @app.get("/api/memory/files")
    def list_memory_files():
        return {"files": sorted(WRITABLE_MEMORY_FILES)}

    @app.get("/api/memory/files/{name:path}")
    def read_memory_file(name: str):
        _validate_memory_name(name)
        return {"name": name, "content": memory.read_file(name)}

    @app.post("/api/memory/files/{name:path}")
    def write_memory_file(name: str, request: SaveMemoryRequest):
        _validate_memory_name(name)
        backup = _backup_memory_file(workspace, memory.memory_dir / name)
        memory.write_file(name, request.content)
        return {"saved": True, "backup": str(backup)}

    return app


def _validate_memory_name(name: str) -> None:
    if name not in WRITABLE_MEMORY_FILES or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="unsupported memory file")


def _backup_memory_file(workspace: Path, path: Path) -> Path:
    backup_dir = workspace / "backups" / "memory"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    backup_path = backup_dir / f"{path.name}.{stamp}.bak"
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path

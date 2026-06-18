from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI

from mini_agent.dashboard.api import register_dashboard_api
from mini_agent.dashboard.auth import create_dashboard_auth
from mini_agent.dashboard.static import register_dashboard_static
from mini_agent.db.migrations import apply_migrations


def create_dashboard_app(
    workspace: Path,
    status: Optional[Dict[str, object]] = None,
    access_token: Optional[str] = None,
    static_dir: Optional[Path] = None,
    plugin_manager: Optional[object] = None,
) -> FastAPI:
    workspace = Path(workspace)
    apply_migrations(workspace / "agent.db")

    app = FastAPI(title="小助手控制台")
    auth = create_dashboard_auth(access_token or "")
    auth.register_routes(app)
    register_dashboard_api(
        app,
        workspace=workspace,
        status={"running": False, **(status or {})},
        require_auth=auth.require_auth,
        plugin_manager=plugin_manager,
    )
    register_dashboard_static(app, auth, static_dir=static_dir)
    return app

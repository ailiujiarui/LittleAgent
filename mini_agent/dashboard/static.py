from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from mini_agent.dashboard.auth import DashboardAuth, login_html


def register_dashboard_static(
    app: FastAPI,
    auth: DashboardAuth,
    static_dir: Optional[Path] = None,
) -> None:
    dist_dir = Path(static_dir) if static_dir is not None else _default_dist_dir()

    @app.get("/assets/{asset_path:path}")
    def serve_asset(asset_path: str, request: Request):
        auth.require_auth(request)
        assets_dir = dist_dir / "assets"
        asset = _resolve_child(assets_dir, asset_path)
        if asset is None or not asset.is_file():
            raise HTTPException(status_code=404, detail="静态资源不存在")
        return FileResponse(asset)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        if not auth.is_authorized(request):
            return login_html()
        return _dashboard_entry(dist_dir)

    @app.get("/{route:path}", response_class=HTMLResponse)
    def spa_fallback(route: str, request: Request):
        if route.startswith("api/"):
            raise HTTPException(status_code=404, detail="接口不存在")
        if not auth.is_authorized(request):
            return login_html()
        return _dashboard_entry(dist_dir)


def _dashboard_entry(dist_dir: Path):
    index_file = dist_dir / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return _missing_build_html()


def _default_dist_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "dashboard-ui" / "dist"


def _resolve_child(root: Path, child: str) -> Optional[Path]:
    root = root.resolve()
    target = (root / child).resolve()
    if target == root or root not in target.parents:
        return None
    return target


def _missing_build_html() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>小助手控制台</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --surface: #ffffff;
      --text: #18202a;
      --muted: #657080;
      --line: #d9e0e8;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      align-items: center;
      background: var(--bg);
      color: var(--text);
      display: grid;
      margin: 0;
      min-height: 100vh;
      padding: 24px;
    }
    main {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      display: grid;
      gap: 14px;
      margin: 0 auto;
      max-width: 560px;
      padding: 24px;
      width: 100%;
    }
    h1 {
      font-size: 22px;
      line-height: 1.25;
      margin: 0;
    }
    p {
      color: var(--muted);
      line-height: 1.7;
      margin: 0;
    }
    code {
      background: #eef2f6;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--text);
      display: inline-block;
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      padding: 2px 6px;
    }
  </style>
</head>
<body>
  <main>
    <h1>小助手控制台</h1>
    <p>控制台前端尚未构建。请进入 <code>dashboard-ui</code> 目录执行 <code>npm run build</code>，构建完成后刷新本页。</p>
    <p>后端服务和现有数据接口已经可用；这里只缺少 Vue 静态页面。</p>
  </main>
</body>
</html>
""",
    )

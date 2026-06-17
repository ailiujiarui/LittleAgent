import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from mini_agent.db.migrations import apply_migrations
from mini_agent.memory.store import WRITABLE_MEMORY_FILES, MemoryStore


class SaveMemoryRequest(BaseModel):
    content: str


class LoginRequest(BaseModel):
    token: str


DASHBOARD_SESSION_COOKIE = "dashboard_session"


def create_dashboard_app(
    workspace: Path,
    status: Optional[Dict[str, object]] = None,
    access_token: Optional[str] = None,
) -> FastAPI:
    workspace = Path(workspace)
    memory = MemoryStore(workspace)
    db_path = workspace / "agent.db"
    apply_migrations(db_path)
    runtime_status = {"running": False, **(status or {})}
    configured_token = access_token or ""
    session_token = secrets.token_urlsafe(32) if configured_token else ""

    app = FastAPI(title="小助手控制台")

    def require_auth(request: Request) -> None:
        if not _request_authorized(request, configured_token, session_token):
            raise HTTPException(status_code=401, detail="未授权")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        if configured_token and not _request_authorized(
            request, configured_token, session_token
        ):
            return _login_html()
        return _dashboard_html()

    @app.post("/api/login")
    def login(request: LoginRequest):
        if configured_token and not secrets.compare_digest(
            request.token, configured_token
        ):
            raise HTTPException(status_code=401, detail="访问令牌不正确")
        response = JSONResponse({"ok": True})
        if session_token:
            response.set_cookie(
                DASHBOARD_SESSION_COOKIE,
                session_token,
                httponly=True,
                max_age=12 * 60 * 60,
                samesite="lax",
            )
        return response

    @app.get("/api/status", dependencies=[Depends(require_auth)])
    def get_status():
        return {"workspace": str(workspace), **runtime_status}

    @app.get("/api/memory/files", dependencies=[Depends(require_auth)])
    def list_memory_files():
        return {"files": sorted(WRITABLE_MEMORY_FILES)}

    @app.get("/api/memory/files/{name:path}", dependencies=[Depends(require_auth)])
    def read_memory_file(name: str):
        _validate_memory_name(name)
        return {"name": name, "content": memory.read_file(name)}

    @app.post("/api/memory/files/{name:path}", dependencies=[Depends(require_auth)])
    def write_memory_file(name: str, request: SaveMemoryRequest):
        _validate_memory_name(name)
        backup = _backup_memory_file(workspace, memory.memory_dir / name)
        memory.write_file(name, request.content)
        return {"saved": True, "backup": str(backup)}

    @app.get("/api/sessions", dependencies=[Depends(require_auth)])
    def list_sessions(limit: int = 50):
        limit = _clamp_limit(limit)
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                select
                    s.id,
                    s.channel,
                    s.chat_id,
                    s.created_at,
                    s.updated_at,
                    count(m.id) as message_count
                from sessions s
                left join messages m on m.session_id = s.id
                group by s.id, s.channel, s.chat_id, s.created_at, s.updated_at
                order by s.updated_at desc, s.id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return {
            "sessions": [
                {
                    "id": row[0],
                    "channel": row[1],
                    "chat_id": row[2],
                    "created_at": row[3],
                    "updated_at": row[4],
                    "message_count": int(row[5]),
                }
                for row in rows
            ]
        }

    @app.get("/api/sessions/{session_id:path}", dependencies=[Depends(require_auth)])
    def get_session(session_id: str):
        with sqlite3.connect(db_path) as conn:
            session = conn.execute(
                """
                select
                    s.id,
                    s.channel,
                    s.chat_id,
                    s.created_at,
                    s.updated_at,
                    count(m.id) as message_count
                from sessions s
                left join messages m on m.session_id = s.id
                where s.id = ?
                group by s.id, s.channel, s.chat_id, s.created_at, s.updated_at
                """,
                (session_id,),
            ).fetchone()
            if session is None:
                raise HTTPException(status_code=404, detail="会话不存在")

            messages = conn.execute(
                """
                select id, role, content, created_at
                from messages
                where session_id = ?
                order by id
                """,
                (session_id,),
            ).fetchall()

        return {
            "session": {
                "id": session[0],
                "channel": session[1],
                "chat_id": session[2],
                "created_at": session[3],
                "updated_at": session[4],
                "message_count": int(session[5]),
            },
            "messages": [
                {
                    "id": row[0],
                    "role": row[1],
                    "content": row[2],
                    "created_at": row[3],
                }
                for row in messages
            ],
        }

    @app.get("/api/events", dependencies=[Depends(require_auth)])
    def list_events(limit: int = 50):
        limit = _clamp_limit(limit)
        events: List[Dict[str, Any]] = []
        with sqlite3.connect(db_path) as conn:
            runtime_rows = conn.execute(
                """
                select id, event_type, payload_json, created_at
                from runtime_events
                order by created_at desc, id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
            tool_rows = conn.execute(
                """
                select id, session_id, tool_name, arguments_json, result_json, created_at
                from tool_events
                order by created_at desc, id desc
                limit ?
                """,
                (limit,),
            ).fetchall()

        for row in runtime_rows:
            events.append(
                {
                    "kind": "runtime",
                    "id": row[0],
                    "event_type": row[1],
                    "payload": _parse_json(row[2]),
                    "created_at": row[3],
                }
            )
        for row in tool_rows:
            events.append(
                {
                    "kind": "tool",
                    "id": row[0],
                    "session_id": row[1],
                    "tool_name": row[2],
                    "arguments": _parse_json(row[3]),
                    "result": _parse_json(row[4]),
                    "created_at": row[5],
                }
            )

        events.sort(key=lambda event: (event["created_at"], event["id"]), reverse=True)
        return {"events": events[:limit]}

    @app.get("/api/proactive", dependencies=[Depends(require_auth)])
    def list_proactive_items(limit: int = 50):
        limit = _clamp_limit(limit)
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                select id, source, item_key, title, url, judged_at, pushed_at
                from proactive_items
                order by id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return {
            "items": [
                {
                    "id": row[0],
                    "source": row[1],
                    "item_key": row[2],
                    "title": row[3],
                    "url": row[4],
                    "judged_at": row[5],
                    "pushed_at": row[6],
                }
                for row in rows
            ]
        }

    @app.get("/api/drift", dependencies=[Depends(require_auth)])
    def list_drift_runs(limit: int = 50):
        limit = _clamp_limit(limit)
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                select id, started_at, finished_at, status, summary
                from drift_runs
                order by id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return {
            "runs": [
                {
                    "id": row[0],
                    "started_at": row[1],
                    "finished_at": row[2],
                    "status": row[3],
                    "summary": row[4],
                }
                for row in rows
            ]
        }

    return app


def _request_authorized(
    request: Request, access_token: str, session_token: str = ""
) -> bool:
    if not access_token:
        return True

    cookie_token = request.cookies.get(DASHBOARD_SESSION_COOKIE, "")
    if session_token and cookie_token:
        if secrets.compare_digest(cookie_token, session_token):
            return True

    supplied = _bearer_token(request.headers.get("Authorization", ""))
    if not supplied:
        supplied = request.headers.get("X-Dashboard-Token", "")
    return secrets.compare_digest(str(supplied), access_token)


def _bearer_token(header: str) -> str:
    parts = header.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return ""


def _validate_memory_name(name: str) -> None:
    if name not in WRITABLE_MEMORY_FILES or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="不支持的记忆文件")


def _backup_memory_file(workspace: Path, path: Path) -> Path:
    backup_dir = workspace / "backups" / "memory"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    backup_path = backup_dir / f"{path.name}.{stamp}.bak"
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), 200))


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        return {"raw": text}


def _login_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>小助手控制台登录</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --surface: #ffffff;
      --text: #18202a;
      --muted: #657080;
      --line: #d9e0e8;
      --accent: #1769aa;
      --accent-strong: #0e4f85;
      --focus: rgba(23, 105, 170, 0.22);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * {
      box-sizing: border-box;
    }

    body {
      align-items: center;
      background: var(--bg);
      color: var(--text);
      display: grid;
      min-height: 100vh;
      margin: 0;
      padding: 24px;
    }

    main {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      display: grid;
      gap: 18px;
      margin: 0 auto;
      max-width: 420px;
      padding: 24px;
      width: 100%;
    }

    h1 {
      font-size: 20px;
      margin: 0;
    }

    p {
      color: var(--muted);
      line-height: 1.6;
      margin: 0;
    }

    .error {
      color: #b3261e;
      font-size: 14px;
    }

    form {
      display: grid;
      gap: 12px;
    }

    label {
      font-size: 14px;
      font-weight: 700;
    }

    input {
      border: 1px solid var(--line);
      border-radius: 7px;
      font: inherit;
      min-height: 40px;
      padding: 0 12px;
      width: 100%;
    }

    input:focus-visible,
    button:focus-visible {
      outline: 3px solid var(--focus);
      outline-offset: 2px;
    }

    button {
      background: var(--accent);
      border: 0;
      border-radius: 7px;
      color: #fff;
      cursor: pointer;
      font: inherit;
      font-weight: 700;
      min-height: 40px;
      padding: 0 14px;
    }

    button:hover {
      background: var(--accent-strong);
    }
  </style>
</head>
<body>
  <main>
    <h1>小助手控制台</h1>
    <p>此控制台已启用访问令牌保护。请输入配置中的控制台访问令牌。</p>
    <form id="token-form">
      <label for="token-input">访问令牌</label>
      <input id="token-input" name="token" type="password" autocomplete="current-password" required>
      <p class="error" id="login-error" hidden>访问令牌不正确，请重新输入。</p>
      <button type="submit">进入控制台</button>
    </form>
  </main>
  <script>
    document.getElementById("token-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const token = document.getElementById("token-input").value.trim();
      const error = document.getElementById("login-error");
      error.hidden = true;
      if (!token) {
        return;
      }
      try {
        const response = await fetch("/api/login", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({token})
        });
        if (response.ok) {
          window.location.href = "/";
          return;
        }
      } catch (err) {
        // 保持统一中文错误提示。
      }
      error.hidden = false;
    });
  </script>
</body>
</html>
"""


def _dashboard_html() -> str:
    return """<!doctype html>
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
      --surface-2: #eef2f6;
      --text: #18202a;
      --muted: #657080;
      --line: #d9e0e8;
      --accent: #1769aa;
      --accent-strong: #0e4f85;
      --ok: #0f7b47;
      --warn: #ad5a00;
      --bad: #b42318;
      --focus: rgba(23, 105, 170, 0.22);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
    }

    button,
    textarea {
      font: inherit;
    }

    button {
      border: 1px solid transparent;
      border-radius: 7px;
      cursor: pointer;
      min-height: 36px;
      padding: 0 12px;
      transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
      white-space: nowrap;
    }

    button:focus-visible,
    textarea:focus-visible {
      outline: 3px solid var(--focus);
      outline-offset: 2px;
    }

    button.primary {
      background: var(--accent);
      color: #fff;
    }

    button.primary:hover {
      background: var(--accent-strong);
    }

    button.secondary {
      background: var(--surface);
      border-color: var(--line);
      color: var(--text);
    }

    button.secondary:hover {
      background: var(--surface-2);
    }

    button.ghost {
      background: transparent;
      color: var(--muted);
      padding-inline: 8px;
    }

    button.ghost:hover {
      background: var(--surface-2);
      color: var(--text);
    }

    button[disabled] {
      cursor: not-allowed;
      opacity: 0.58;
    }

    .app-shell {
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto 1fr;
    }

    .topbar {
      background: var(--surface);
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      min-height: 64px;
      padding: 12px 24px;
    }

    .brand {
      min-width: 0;
    }

    .brand h1 {
      font-size: 18px;
      font-weight: 700;
      line-height: 1.2;
      margin: 0;
    }

    .brand p {
      color: var(--muted);
      font-size: 13px;
      margin: 4px 0 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .status-strip {
      align-items: center;
      display: flex;
      gap: 10px;
      min-width: fit-content;
    }

    .pill {
      align-items: center;
      background: var(--surface-2);
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--muted);
      display: inline-flex;
      font-size: 13px;
      font-weight: 600;
      gap: 8px;
      min-height: 32px;
      padding: 0 12px;
    }

    .dot {
      border-radius: 50%;
      display: inline-block;
      height: 8px;
      width: 8px;
    }

    .dot.ok {
      background: var(--ok);
    }

    .dot.warn {
      background: var(--warn);
    }

    .dot.bad {
      background: var(--bad);
    }

    .layout {
      display: grid;
      grid-template-columns: 300px minmax(0, 1fr);
      min-height: 0;
    }

    aside {
      background: var(--surface);
      border-right: 1px solid var(--line);
      min-height: calc(100vh - 64px);
      padding: 20px;
    }

    main {
      min-width: 0;
      padding: 22px;
    }

    .section-title {
      align-items: center;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }

    .section-title h2 {
      font-size: 14px;
      letter-spacing: 0;
      line-height: 1.2;
      margin: 0;
    }

    .file-list {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }

    .file-button {
      align-items: center;
      background: transparent;
      border: 1px solid transparent;
      border-radius: 7px;
      color: var(--text);
      display: flex;
      justify-content: space-between;
      min-height: 40px;
      padding: 0 10px;
      text-align: left;
      width: 100%;
    }

    .file-button:hover {
      background: var(--surface-2);
    }

    .file-button.active {
      background: #e7f1fa;
      border-color: #bdd8ed;
      color: var(--accent-strong);
      font-weight: 700;
    }

    .file-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .chevron {
      color: var(--muted);
      flex: 0 0 auto;
      margin-left: 8px;
    }

    .workspace-block {
      background: var(--surface-2);
      border: 1px solid var(--line);
      border-radius: 8px;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      line-height: 1.5;
      margin-top: 18px;
      overflow-wrap: anywhere;
      padding: 12px;
    }

    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      min-height: calc(100vh - 108px);
      overflow: hidden;
    }

    .panel-head {
      align-items: center;
      border-bottom: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      gap: 16px;
      min-height: 64px;
      padding: 14px 16px;
    }

    .panel-head h2 {
      font-size: 16px;
      margin: 0;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .panel-actions {
      align-items: center;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }

    .editor-wrap {
      display: grid;
      grid-template-rows: minmax(380px, 1fr) auto;
      min-height: calc(100vh - 173px);
    }

    #memory-editor {
      background: #fbfcfd;
      border: 0;
      color: var(--text);
      line-height: 1.58;
      min-height: 380px;
      padding: 18px;
      resize: vertical;
      width: 100%;
    }

    .message-row {
      align-items: center;
      background: #fbfcfd;
      border-top: 1px solid var(--line);
      color: var(--muted);
      display: flex;
      font-size: 13px;
      gap: 10px;
      justify-content: space-between;
      min-height: 46px;
      padding: 10px 16px;
    }

    .message-row strong {
      color: var(--text);
      font-weight: 700;
    }

    .message-row.error {
      background: #fff7f6;
      color: var(--bad);
    }

    .message-row.success {
      background: #f1fbf5;
      color: var(--ok);
    }

    .empty-state {
      align-items: center;
      color: var(--muted);
      display: flex;
      justify-content: center;
      min-height: 260px;
      padding: 24px;
      text-align: center;
    }

    .data-band {
      display: grid;
      gap: 14px;
      margin-top: 18px;
    }

    .data-grid {
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .data-section {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      min-width: 0;
      overflow: hidden;
    }

    .data-section h3 {
      border-bottom: 1px solid var(--line);
      font-size: 14px;
      margin: 0;
      padding: 12px 14px;
    }

    .data-list {
      display: grid;
      gap: 1px;
      max-height: 260px;
      overflow: auto;
    }

    .data-item {
      background: #fbfcfd;
      display: grid;
      gap: 4px;
      min-height: 56px;
      padding: 10px 14px;
    }

    .data-item strong {
      font-size: 13px;
      line-height: 1.3;
      overflow-wrap: anywhere;
    }

    .data-item span {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
      overflow-wrap: anywhere;
    }

    @media (max-width: 820px) {
      .topbar {
        align-items: flex-start;
        flex-direction: column;
        padding: 14px 16px;
      }

      .brand p {
        white-space: normal;
      }

      .layout {
        grid-template-columns: 1fr;
      }

      aside {
        border-bottom: 1px solid var(--line);
        border-right: 0;
        min-height: auto;
        padding: 16px;
      }

      main {
        padding: 16px;
      }

      .panel {
        min-height: auto;
      }

      .panel-head {
        align-items: flex-start;
        flex-direction: column;
      }

      .panel-actions {
        justify-content: flex-start;
        width: 100%;
      }

      .data-grid {
        grid-template-columns: 1fr;
      }

      .editor-wrap {
        min-height: auto;
      }

      #memory-editor {
        min-height: 420px;
      }
    }
  </style>
</head>
<body>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <h1>小助手控制台</h1>
        <p id="workspace-path">正在读取工作区...</p>
      </div>
      <div class="status-strip" aria-live="polite">
        <span class="pill" id="runtime-status"><span class="dot warn"></span>运行状态：检查中</span>
        <button class="secondary" id="refresh-button" type="button" title="刷新状态和数据">刷新</button>
      </div>
    </header>

    <div class="layout">
      <aside>
        <div class="section-title">
          <h2>记忆文件</h2>
          <button class="ghost" id="reload-files-button" type="button" title="重新读取记忆文件列表">重载</button>
        </div>
        <div id="memory-files" class="file-list" aria-label="记忆文件"></div>
        <div class="workspace-block" id="workspace-details">工作区路径会显示在这里。</div>
      </aside>

      <main>
        <section class="panel" aria-labelledby="editor-title">
          <div class="panel-head">
            <h2 id="editor-title">选择记忆文件</h2>
            <div class="panel-actions">
              <button class="secondary" id="reload-file-button" type="button" disabled>重新读取</button>
              <button class="primary" id="save-button" type="button" disabled>保存</button>
            </div>
          </div>
          <div class="editor-wrap">
            <textarea id="memory-editor" spellcheck="false" disabled placeholder="从左侧选择一个记忆文件。"></textarea>
            <div class="message-row" id="dashboard-message">
              <span>正在连接控制台接口。</span>
              <span id="dirty-state">未选择文件</span>
            </div>
          </div>
        </section>

        <section class="data-band" aria-label="运行数据">
          <div class="data-grid">
            <section class="data-section" aria-labelledby="sessions-title">
              <h3 id="sessions-title">最近会话</h3>
              <div id="session-list" class="data-list"></div>
            </section>
            <section class="data-section" aria-labelledby="events-title">
              <h3 id="events-title">运行事件</h3>
              <div id="event-list" class="data-list"></div>
            </section>
            <section class="data-section" aria-labelledby="proactive-title">
              <h3 id="proactive-title">主动推送</h3>
              <div id="proactive-list" class="data-list"></div>
            </section>
            <section class="data-section" aria-labelledby="drift-title">
              <h3 id="drift-title">漂移任务</h3>
              <div id="drift-list" class="data-list"></div>
            </section>
          </div>
        </section>
      </main>
    </div>
  </div>

  <script>
    const state = {
      files: [],
      selectedFile: null,
      originalContent: "",
      dirty: false
    };

    const el = {
      runtimeStatus: document.getElementById("runtime-status"),
      workspacePath: document.getElementById("workspace-path"),
      workspaceDetails: document.getElementById("workspace-details"),
      memoryFiles: document.getElementById("memory-files"),
      editorTitle: document.getElementById("editor-title"),
      editor: document.getElementById("memory-editor"),
      saveButton: document.getElementById("save-button"),
      reloadFileButton: document.getElementById("reload-file-button"),
      refreshButton: document.getElementById("refresh-button"),
      reloadFilesButton: document.getElementById("reload-files-button"),
      message: document.getElementById("dashboard-message"),
      dirtyState: document.getElementById("dirty-state"),
      sessionList: document.getElementById("session-list"),
      eventList: document.getElementById("event-list"),
      proactiveList: document.getElementById("proactive-list"),
      driftList: document.getElementById("drift-list")
    };

    function setMessage(text, kind = "") {
      el.message.className = "message-row" + (kind ? " " + kind : "");
      el.message.firstElementChild.textContent = text;
    }

    function setStatus(label, kind) {
      const dotClass = kind === "ok" ? "ok" : kind === "bad" ? "bad" : "warn";
      el.runtimeStatus.innerHTML = '<span class="dot ' + dotClass + '"></span>运行状态：' + label;
    }

    function updateDirtyState() {
      state.dirty = state.selectedFile !== null && el.editor.value !== state.originalContent;
      el.saveButton.disabled = !state.selectedFile || !state.dirty;
      el.reloadFileButton.disabled = !state.selectedFile;
      el.dirtyState.textContent = state.selectedFile
        ? (state.dirty ? "有未保存修改" : "已保存")
        : "未选择文件";
    }

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, Object.assign({}, options, {
        credentials: "same-origin",
        headers: options.headers || {}
      }));
      if (!response.ok) {
        let detail = "请求失败";
        try {
          const payload = await response.json();
          detail = payload.detail || detail;
        } catch (err) {
          detail = "请求失败（HTTP " + response.status + "）";
        }
        throw new Error(detail);
      }
      return response.json();
    }

    async function loadStatus() {
      try {
        const status = await fetchJson("/api/status");
        const workspace = status.workspace || "未知工作区";
        el.workspacePath.textContent = workspace;
        el.workspaceDetails.textContent = workspace;
        setStatus(status.running ? "助手运行中" : "控制台在线", status.running ? "ok" : "warn");
      } catch (error) {
        setStatus("接口离线", "bad");
        setMessage("无法读取控制台状态：" + error.message, "error");
      }
    }

    async function loadFiles() {
      try {
        const payload = await fetchJson("/api/memory/files");
        state.files = payload.files || [];
        renderFiles();
        if (!state.selectedFile && state.files.length > 0) {
          await selectFile(state.files[0]);
        }
      } catch (error) {
        el.memoryFiles.innerHTML = '<div class="empty-state">无法读取记忆文件。</div>';
        setMessage("无法读取记忆文件：" + error.message, "error");
      }
    }

    async function loadOperationalData() {
      try {
        const sessions = await fetchJson("/api/sessions");
        const events = await fetchJson("/api/events");
        const proactive = await fetchJson("/api/proactive");
        const drift = await fetchJson("/api/drift");

        renderDataList(el.sessionList, sessions.sessions || [], (item) => ({
          title: item.id,
          meta: item.channel + " " + item.chat_id + "，" + item.message_count + " 条消息"
        }));
        renderDataList(el.eventList, events.events || [], (item) => ({
          title: item.kind === "tool" ? "工具：" + item.tool_name : "运行：" + item.event_type,
          meta: item.created_at || ""
        }));
        renderDataList(el.proactiveList, proactive.items || [], (item) => ({
          title: item.title || item.item_key,
          meta: (item.pushed_at ? "已推送 " + item.pushed_at : "已判断 " + (item.judged_at || "等待中")) + "，" + item.source
        }));
        renderDataList(el.driftList, drift.runs || [], (item) => ({
          title: item.status,
          meta: (item.finished_at || item.started_at || "") + "，" + item.summary
        }));
      } catch (error) {
        renderDataList(el.sessionList, [], null, "无法读取运行数据。");
        renderDataList(el.eventList, [], null, "无法读取运行数据。");
        renderDataList(el.proactiveList, [], null, "无法读取运行数据。");
        renderDataList(el.driftList, [], null, "无法读取运行数据。");
      }
    }

    function renderDataList(target, items, mapper, emptyText = "暂无记录。") {
      target.innerHTML = "";
      if (!items.length) {
        const empty = document.createElement("div");
        empty.className = "data-item";
        const text = document.createElement("span");
        text.textContent = emptyText;
        empty.appendChild(text);
        target.appendChild(empty);
        return;
      }

      for (const item of items.slice(0, 10)) {
        const view = mapper(item);
        const row = document.createElement("div");
        row.className = "data-item";
        const title = document.createElement("strong");
        title.textContent = view.title || "未命名";
        const meta = document.createElement("span");
        meta.textContent = view.meta || "";
        row.appendChild(title);
        row.appendChild(meta);
        target.appendChild(row);
      }
    }

    function renderFiles() {
      if (state.files.length === 0) {
        el.memoryFiles.innerHTML = '<div class="empty-state">没有可编辑的记忆文件。</div>';
        return;
      }

      el.memoryFiles.innerHTML = "";
      for (const file of state.files) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "file-button" + (file === state.selectedFile ? " active" : "");
        button.innerHTML = '<span class="file-name"></span><span class="chevron">›</span>';
        button.querySelector(".file-name").textContent = file;
        button.addEventListener("click", () => selectFile(file));
        el.memoryFiles.appendChild(button);
      }
    }

    async function selectFile(name) {
      if (state.dirty) {
        const discard = window.confirm("当前文件有未保存修改，确定放弃这些修改吗？");
        if (!discard) {
          return;
        }
      }

      state.selectedFile = name;
      renderFiles();
      el.editorTitle.textContent = name;
      el.editor.disabled = true;
      setMessage("正在读取 " + name + "...");

      try {
        const payload = await fetchJson("/api/memory/files/" + encodeURIComponent(name));
        state.originalContent = payload.content || "";
        el.editor.value = state.originalContent;
        el.editor.disabled = false;
        setMessage("已读取 " + name + "。");
        updateDirtyState();
      } catch (error) {
        el.editor.value = "";
        el.editor.disabled = true;
        setMessage("无法读取 " + name + "：" + error.message, "error");
        updateDirtyState();
      }
    }

    async function saveCurrentFile() {
      if (!state.selectedFile || !state.dirty) {
        updateDirtyState();
        return;
      }

      el.saveButton.disabled = true;
      setMessage("正在保存 " + state.selectedFile + "...");

      try {
        const payload = await fetchJson("/api/memory/files/" + encodeURIComponent(state.selectedFile), {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({content: el.editor.value})
        });
        state.originalContent = el.editor.value;
        updateDirtyState();
        setMessage("已保存。备份文件：" + payload.backup, "success");
      } catch (error) {
        setMessage("保存失败：" + error.message, "error");
        updateDirtyState();
      }
    }

    async function refreshAll() {
      setMessage("正在刷新控制台...");
      await Promise.all([loadStatus(), loadFiles(), loadOperationalData()]);
      if (state.selectedFile) {
        await selectFile(state.selectedFile);
      }
    }

    el.editor.addEventListener("input", updateDirtyState);
    el.saveButton.addEventListener("click", saveCurrentFile);
    el.reloadFileButton.addEventListener("click", () => state.selectedFile && selectFile(state.selectedFile));
    el.refreshButton.addEventListener("click", refreshAll);
    el.reloadFilesButton.addEventListener("click", loadFiles);

    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        saveCurrentFile();
      }
    });

    refreshAll();
  </script>
</body>
</html>
"""

import secrets
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel


DASHBOARD_SESSION_COOKIE = "dashboard_session"


class LoginRequest(BaseModel):
    token: str


@dataclass
class DashboardAuth:
    access_token: str
    session_token: str

    def is_authorized(self, request: Request) -> bool:
        if not self.access_token:
            return True

        cookie_token = request.cookies.get(DASHBOARD_SESSION_COOKIE, "")
        if self.session_token and cookie_token:
            if secrets.compare_digest(cookie_token, self.session_token):
                return True

        supplied = _bearer_token(request.headers.get("Authorization", ""))
        if not supplied:
            supplied = request.headers.get("X-Dashboard-Token", "")
        return secrets.compare_digest(str(supplied), self.access_token)

    def require_auth(self, request: Request) -> None:
        if not self.is_authorized(request):
            raise HTTPException(status_code=401, detail="未授权")

    def register_routes(self, app: FastAPI) -> None:
        @app.post("/api/login")
        def login(request: LoginRequest):
            if self.access_token and not secrets.compare_digest(
                request.token,
                self.access_token,
            ):
                raise HTTPException(status_code=401, detail="访问令牌不正确")
            response = JSONResponse({"ok": True})
            if self.session_token:
                response.set_cookie(
                    DASHBOARD_SESSION_COOKIE,
                    self.session_token,
                    httponly=True,
                    max_age=12 * 60 * 60,
                    samesite="lax",
                )
            return response


def create_dashboard_auth(access_token: str = "") -> DashboardAuth:
    configured_token = access_token or ""
    session_token = secrets.token_urlsafe(32) if configured_token else ""
    return DashboardAuth(
        access_token=configured_token,
        session_token=session_token,
    )


def login_html() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html>
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
      gap: 18px;
      margin: 0 auto;
      max-width: 420px;
      padding: 24px;
      width: 100%;
    }
    h1 { font-size: 20px; margin: 0; }
    p { color: var(--muted); line-height: 1.6; margin: 0; }
    .error { color: #b3261e; font-size: 14px; }
    form { display: grid; gap: 12px; }
    label { font-size: 14px; font-weight: 700; }
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
    button:hover { background: var(--accent-strong); }
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
      }
      error.hidden = false;
    });
  </script>
</body>
</html>
""",
    )


def _bearer_token(header: str) -> str:
    parts = header.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return ""

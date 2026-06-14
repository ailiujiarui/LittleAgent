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
        return _dashboard_html()

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


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mini Agent Dashboard</title>
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
        <h1>Mini Agent Dashboard</h1>
        <p id="workspace-path">Loading workspace...</p>
      </div>
      <div class="status-strip" aria-live="polite">
        <span class="pill" id="runtime-status"><span class="dot warn"></span>Checking</span>
        <button class="secondary" id="refresh-button" type="button" title="Refresh status and memory list">Refresh</button>
      </div>
    </header>

    <div class="layout">
      <aside>
        <div class="section-title">
          <h2>Memory Files</h2>
          <button class="ghost" id="reload-files-button" type="button" title="Reload memory files">Reload</button>
        </div>
        <div id="memory-files" class="file-list" aria-label="Memory files"></div>
        <div class="workspace-block" id="workspace-details">Workspace path will appear here.</div>
      </aside>

      <main>
        <section class="panel" aria-labelledby="editor-title">
          <div class="panel-head">
            <h2 id="editor-title">Select a memory file</h2>
            <div class="panel-actions">
              <button class="secondary" id="reload-file-button" type="button" disabled>Reload file</button>
              <button class="primary" id="save-button" type="button" disabled>Save</button>
            </div>
          </div>
          <div class="editor-wrap">
            <textarea id="memory-editor" spellcheck="false" disabled placeholder="Select a memory file from the left."></textarea>
            <div class="message-row" id="dashboard-message">
              <span>Dashboard API is loading.</span>
              <span id="dirty-state">No file selected</span>
            </div>
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
      dirtyState: document.getElementById("dirty-state")
    };

    function setMessage(text, kind = "") {
      el.message.className = "message-row" + (kind ? " " + kind : "");
      el.message.firstElementChild.textContent = text;
    }

    function setStatus(label, kind) {
      const dotClass = kind === "ok" ? "ok" : kind === "bad" ? "bad" : "warn";
      el.runtimeStatus.innerHTML = '<span class="dot ' + dotClass + '"></span>' + label;
    }

    function updateDirtyState() {
      state.dirty = state.selectedFile !== null && el.editor.value !== state.originalContent;
      el.saveButton.disabled = !state.selectedFile || !state.dirty;
      el.reloadFileButton.disabled = !state.selectedFile;
      el.dirtyState.textContent = state.selectedFile
        ? (state.dirty ? "Unsaved changes" : "Saved")
        : "No file selected";
    }

    async function fetchJson(url, options) {
      const response = await fetch(url, options);
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || response.statusText);
      }
      return response.json();
    }

    async function loadStatus() {
      try {
        const status = await fetch("/api/status").then((response) => response.json());
        const workspace = status.workspace || "Unknown workspace";
        el.workspacePath.textContent = workspace;
        el.workspaceDetails.textContent = workspace;
        setStatus(status.running ? "Agent running" : "Dashboard online", status.running ? "ok" : "warn");
      } catch (error) {
        setStatus("API offline", "bad");
        setMessage("Cannot load dashboard status: " + error.message, "error");
      }
    }

    async function loadFiles() {
      try {
        const payload = await fetch("/api/memory/files").then((response) => response.json());
        state.files = payload.files || [];
        renderFiles();
        if (!state.selectedFile && state.files.length > 0) {
          await selectFile(state.files[0]);
        }
      } catch (error) {
        el.memoryFiles.innerHTML = '<div class="empty-state">Cannot load memory files.</div>';
        setMessage("Cannot load memory files: " + error.message, "error");
      }
    }

    function renderFiles() {
      if (state.files.length === 0) {
        el.memoryFiles.innerHTML = '<div class="empty-state">No writable memory files found.</div>';
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
        const discard = window.confirm("Current file has unsaved changes. Discard them?");
        if (!discard) {
          return;
        }
      }

      state.selectedFile = name;
      renderFiles();
      el.editorTitle.textContent = name;
      el.editor.disabled = true;
      setMessage("Loading " + name + "...");

      try {
        const payload = await fetchJson("/api/memory/files/" + encodeURIComponent(name));
        state.originalContent = payload.content || "";
        el.editor.value = state.originalContent;
        el.editor.disabled = false;
        setMessage("Loaded " + name + ".");
        updateDirtyState();
      } catch (error) {
        el.editor.value = "";
        el.editor.disabled = true;
        setMessage("Cannot load " + name + ": " + error.message, "error");
        updateDirtyState();
      }
    }

    async function saveCurrentFile() {
      if (!state.selectedFile || !state.dirty) {
        updateDirtyState();
        return;
      }

      el.saveButton.disabled = true;
      setMessage("Saving " + state.selectedFile + "...");

      try {
        const payload = await fetchJson("/api/memory/files/" + encodeURIComponent(state.selectedFile), {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({content: el.editor.value})
        });
        state.originalContent = el.editor.value;
        updateDirtyState();
        setMessage("Saved. Backup: " + payload.backup, "success");
      } catch (error) {
        setMessage("Save failed: " + error.message, "error");
        updateDirtyState();
      }
    }

    async function refreshAll() {
      setMessage("Refreshing dashboard...");
      await Promise.all([loadStatus(), loadFiles()]);
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

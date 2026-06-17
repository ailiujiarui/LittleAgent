# Vue Dashboard Plugin Hotplug Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the inline Dashboard HTML with a standalone Vue module served by Python, and add lightweight Dashboard-managed plugin enable/disable/reload with runtime hotplug where possible.

**Architecture:** Keep the Python Agent as the single production process. Split Dashboard backend into auth, API, and static serving modules; Vue lives in `dashboard-ui/` and builds to static assets served by FastAPI. Plugin hotplug is implemented in `mini_agent.plugins` with SQLite state, source-aware tool/event cleanup, optional `teardown(ctx)`, and runtime-only immediate effect.

**Tech Stack:** Python 3.9+, FastAPI, SQLite, Pydantic 2, pytest, Vue 3, Vite, TypeScript, npm

---

## File Structure

**Create**
- `mini_agent/db/migrations/002_plugin_states.sql`: plugin state migration.
- `mini_agent/plugins/state.py`: SQLite store for plugin enabled/locked/load-error state.
- `mini_agent/plugins/catalog.py`: lightweight discovery metadata for builtin and workspace plugins.
- `mini_agent/dashboard/auth.py`: login, session cookie, auth dependency helpers.
- `mini_agent/dashboard/api.py`: JSON API routes for status, memory, operational data, and plugins.
- `mini_agent/dashboard/static.py`: Vue `dist` static mounting and Chinese missing-build fallback.
- `dashboard-ui/package.json`: Vue app scripts and dependencies.
- `dashboard-ui/vite.config.ts`: Vite config.
- `dashboard-ui/tsconfig.json`: TypeScript config.
- `dashboard-ui/index.html`: Vue entry HTML.
- `dashboard-ui/src/main.ts`: Vue mount entry.
- `dashboard-ui/src/App.vue`: app shell composition.
- `dashboard-ui/src/api/client.ts`: fetch wrapper with Chinese error fallback.
- `dashboard-ui/src/api/types.ts`: Dashboard API response types.
- `dashboard-ui/src/components/AppShell.vue`: topbar/sidebar/content layout.
- `dashboard-ui/src/components/StatusBadge.vue`: compact status label.
- `dashboard-ui/src/components/ConfirmDialog.vue`: Chinese confirm dialog.
- `dashboard-ui/src/views/OverviewView.vue`: status overview.
- `dashboard-ui/src/views/MemoryView.vue`: memory file editor.
- `dashboard-ui/src/views/PluginsView.vue`: plugin list and actions.
- `dashboard-ui/src/views/SessionsView.vue`: recent sessions.
- `dashboard-ui/src/views/EventsView.vue`: runtime events.
- `dashboard-ui/src/views/ProactiveView.vue`: proactive records.
- `dashboard-ui/src/views/DriftView.vue`: drift records.
- `dashboard-ui/src/style.css`: shared restrained dashboard styling.

**Modify**
- `mini_agent/tools/registry.py`: store source metadata and unregister by source.
- `mini_agent/plugins/context.py`: track tools/events per plugin runtime.
- `mini_agent/plugins/manager.py`: support state-aware discover/load/unload/reload.
- `mini_agent/app.py`: pass `self.plugins` into Dashboard and share builtin plugin specs.
- `mini_agent/dashboard/server.py`: shrink to `create_dashboard_app()` composition.
- `mini_agent/__main__.py`: keep standalone dashboard compatible with Vue static serving.
- `mini_agent/db/migrations.py`: no behavior change expected, but tests must verify `002` migration.
- `pyproject.toml`: no new Python dependencies expected.
- `.gitignore`: ignore `dashboard-ui/node_modules/` and local Vite artifacts if needed.
- `README.zh-CN.md`: document Vue build, plugin management, and workspace plugin default-disabled behavior.
- `tests/test_config_init_db.py`: migration/state tests.
- `tests/test_tool_registry.py`: source metadata unregister tests.
- `tests/test_plugins.py`: plugin state and hotplug lifecycle tests.
- `tests/test_app_cli.py`: runtime Dashboard plugin manager injection tests.
- `tests/test_dashboard.py`: Dashboard API/static/auth/plugin tests.

---

### Task 1: Plugin State Migration And Store

**Files:**
- Create: `mini_agent/db/migrations/002_plugin_states.sql`
- Create: `mini_agent/plugins/state.py`
- Modify: `tests/test_config_init_db.py`
- Test: `tests/test_plugins.py`

- [ ] **Step 1: Write failing migration test**

Add a test that creates a database with only migration `001_init`, then runs `apply_migrations()` and verifies `plugin_states` and `002_plugin_states`.

```python
def test_apply_migrations_adds_plugin_states_to_existing_database(tmp_path):
    from mini_agent.db.migrations import apply_migrations

    db_path = tmp_path / "agent.db"
    apply_migrations(db_path)

    # Simulate old DB by removing the new table and migration record once task code exists.
    with sqlite3.connect(db_path) as conn:
        conn.execute("drop table if exists plugin_states")
        conn.execute("delete from schema_migrations where version = '002_plugin_states'")
        conn.commit()

    apply_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        versions = {row[0] for row in conn.execute("select version from schema_migrations")}

    assert "plugin_states" in tables
    assert "002_plugin_states" in versions
```

- [ ] **Step 2: Write failing plugin state store tests**

Add tests for `(source, name)` identity, builtin default enabled, workspace default disabled, explicit update changing `updated_at`, and same-name builtin/workspace isolation.

```python
def test_plugin_state_defaults_and_source_identity(tmp_path):
    from mini_agent.plugins.state import PluginStateStore

    store = PluginStateStore(tmp_path / "agent.db")

    builtin = store.ensure("builtin", "echo", default_enabled=True)
    workspace = store.ensure("workspace", "echo", default_enabled=False)

    assert builtin.enabled is True
    assert workspace.enabled is False
    assert builtin.source == "builtin"
    assert workspace.source == "workspace"
```

- [ ] **Step 3: Run tests to verify failure**

Run: `py -m pytest tests/test_config_init_db.py tests/test_plugins.py -q`

Expected: FAIL because migration and `PluginStateStore` do not exist.

- [ ] **Step 4: Implement migration and state store**

Create `002_plugin_states.sql` with:

```sql
create table if not exists plugin_states (
    source text not null,
    name text not null,
    enabled integer not null,
    locked integer not null default 0,
    last_loaded_at text,
    last_error text not null default '',
    updated_at text not null default current_timestamp,
    primary key (source, name)
);
```

Implement `PluginStateStore` with `ensure()`, `set_enabled()`, `set_loaded()`, `set_error()`, and `get()` methods. Every write explicitly sets `updated_at = current_timestamp`.

- [ ] **Step 5: Run focused tests**

Run: `py -m pytest tests/test_config_init_db.py tests/test_plugins.py -q`

Expected: PASS for new migration/state tests; unrelated plugin tests remain green.

- [ ] **Step 6: Commit**

```bash
git add mini_agent/db/migrations/002_plugin_states.sql mini_agent/plugins/state.py tests/test_config_init_db.py tests/test_plugins.py
git commit -m "增加插件状态迁移和存储"
```

---

### Task 2: Source-Aware Tool Registry

**Files:**
- Modify: `mini_agent/tools/registry.py`
- Modify: `tests/test_tool_registry.py`

- [ ] **Step 1: Write failing source unregister tests**

Add tests that register two plugin tools and one builtin tool, unregister one plugin source, and verify only that source is removed.

```python
def test_tool_registry_unregisters_tools_by_source():
    registry = ToolRegistry()
    registry.register(make_tool("plugin_a"), source_type="plugin", source_name="workspace:demo")
    registry.register(make_tool("plugin_b"), source_type="plugin", source_name="workspace:other")
    registry.register(make_tool("builtin"), source_type="builtin", source_name="core")

    removed = registry.unregister_source("plugin", "workspace:demo")

    assert removed == ["plugin_a"]
    assert registry.has_tool("plugin_a") is False
    assert registry.has_tool("plugin_b") is True
    assert registry.has_tool("builtin") is True
```

- [ ] **Step 2: Run test to verify failure**

Run: `py -m pytest tests/test_tool_registry.py -q`

Expected: FAIL because `unregister_source()` and metadata storage do not exist.

- [ ] **Step 3: Implement metadata tracking**

Keep `register(tool, **metadata)` backward compatible, add `_metadata: Dict[str, Dict[str, Any]]`, and implement:

```python
def unregister_source(self, source_type: str, source_name: str) -> List[str]:
    removed = []
    for name, metadata in list(self._metadata.items()):
        if metadata.get("source_type") == source_type and metadata.get("source_name") == source_name:
            self._tools.pop(name, None)
            self._metadata.pop(name, None)
            removed.append(name)
    return sorted(removed)
```

- [ ] **Step 4: Run focused tests**

Run: `py -m pytest tests/test_tool_registry.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mini_agent/tools/registry.py tests/test_tool_registry.py
git commit -m "支持按来源反注册工具"
```

---

### Task 3: Plugin Catalog And Runtime Tracking

**Files:**
- Create: `mini_agent/plugins/catalog.py`
- Modify: `mini_agent/plugins/context.py`
- Modify: `mini_agent/plugins/manager.py`
- Modify: `tests/test_plugins.py`

- [ ] **Step 1: Write failing catalog tests**

Cover builtin specs, workspace plugin discovery, same-name source separation, and default enabled policy.

```python
def test_plugin_catalog_discovers_builtin_and_workspace_plugins(tmp_path):
    from mini_agent.plugins.catalog import PluginCatalog, builtin_plugin_specs

    (tmp_path / "plugins" / "demo").mkdir(parents=True)
    (tmp_path / "plugins" / "demo" / "plugin.py").write_text("def setup(ctx): pass", encoding="utf-8")

    catalog = PluginCatalog(tmp_path, builtin_plugin_specs())
    plugins = catalog.discover()

    assert ("builtin", "group_messages") in {(p.source, p.name) for p in plugins}
    assert ("workspace", "demo") in {(p.source, p.name) for p in plugins}
```

- [ ] **Step 2: Write failing runtime tracking tests**

Cover that `PluginContext.register_tool()` records the tool name with plugin ID, and `subscribe()` records the event handler by plugin ID.

- [ ] **Step 3: Run tests to verify failure**

Run: `py -m pytest tests/test_plugins.py -q`

Expected: FAIL because catalog/runtime tracking does not exist.

- [ ] **Step 4: Implement catalog**

Create `PluginSpec(source, name, id, setup, plugin_dir, default_enabled, locked)` and `PluginCatalog.discover()`.

Move builtin plugin construction into a reusable function, for example:

```python
def builtin_plugin_specs(xiaohongshu_setup=None) -> Dict[str, PluginSpec]:
    ...
```

Runtime can pass real setup callables. Standalone can use metadata-only specs without executing setup.

- [ ] **Step 5: Implement context tracking**

Allow `PluginContext` to receive `plugin_id` and optional runtime tracker. `register_tool()` registers metadata `source_type="plugin", source_name=plugin_id`; `subscribe()` stores handlers in a structure that can be removed by plugin ID.

- [ ] **Step 6: Run focused tests**

Run: `py -m pytest tests/test_plugins.py -q`

Expected: PASS for catalog/context tests; older plugin tests still pass.

- [ ] **Step 7: Commit**

```bash
git add mini_agent/plugins/catalog.py mini_agent/plugins/context.py mini_agent/plugins/manager.py tests/test_plugins.py
git commit -m "增加插件目录和运行时追踪"
```

---

### Task 4: PluginManager Enable Disable Reload

**Files:**
- Modify: `mini_agent/plugins/manager.py`
- Modify: `mini_agent/plugins/context.py`
- Modify: `tests/test_plugins.py`

- [ ] **Step 1: Write failing lifecycle tests**

Add tests for:
- builtin default enabled and workspace default disabled.
- enabling workspace plugin registers tools/events.
- disabling plugin calls optional `teardown(ctx)` and removes tools/events.
- `setup()` that registers a tool then raises rolls back the tool/event.
- `teardown()` error is recorded but cleanup still happens.
- `reload()` loads updated plugin code.
- locked plugin cannot be disabled.

Representative test:

```python
def test_plugin_setup_failure_rolls_back_registered_tool(tmp_path):
    plugin_dir = tmp_path / "plugins" / "bad"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.py").write_text(
        "from mini_agent.tools.base import Tool\\n"
        "from pydantic import BaseModel\\n"
        "class Args(BaseModel): pass\\n"
        "def setup(ctx):\\n"
        "    ctx.register_tool(Tool('bad_tool', 'bad', Args, lambda args: {}))\\n"
        "    raise RuntimeError('boom')\\n",
        encoding="utf-8",
    )

    manager = PluginManager(workspace=tmp_path, tools=ToolRegistry())
    result = manager.enable("workspace", "bad")

    assert result.loaded is False
    assert manager.tools.has_tool("bad_tool") is False
```

- [ ] **Step 2: Run tests to verify failure**

Run: `py -m pytest tests/test_plugins.py -q`

Expected: FAIL because lifecycle APIs do not exist.

- [ ] **Step 3: Implement lifecycle APIs**

Add `list_plugins()`, `enable(source, name)`, `disable(source, name)`, `reload(source, name)`, `load_enabled()`, and internal cleanup helpers. Use a manager-level `asyncio.Lock` or a sync lock depending on API shape; if public methods are async, update callers/tests accordingly.

The manager must return structured results with `ok`, `plugin`, `requires_restart=False`, and Chinese `message`.

- [ ] **Step 4: Keep startup behavior compatible**

`load_all()` should become a compatibility wrapper around state-aware loading:
- ensure builtin states default enabled.
- ensure workspace states default disabled.
- load only enabled plugins.
- return `PluginLoadResult` compatible with existing `dry_run()` summary.

- [ ] **Step 5: Run focused tests**

Run: `py -m pytest tests/test_plugins.py tests/test_app_cli.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add mini_agent/plugins/manager.py mini_agent/plugins/context.py tests/test_plugins.py tests/test_app_cli.py
git commit -m "实现插件轻量热插拔"
```

---

### Task 5: Dashboard Backend Split And Existing API Preservation

**Files:**
- Create: `mini_agent/dashboard/auth.py`
- Create: `mini_agent/dashboard/api.py`
- Create: `mini_agent/dashboard/static.py`
- Modify: `mini_agent/dashboard/server.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing preservation tests**

Keep existing Dashboard tests for login, memory files, sessions, events, proactive, drift, and Chinese errors. Add tests that `server.py` no longer needs inline HTML behavior except fallback/static entry.

- [ ] **Step 2: Write failing static tests**

Add tests:
- missing Vue build returns Chinese page with “控制台前端尚未构建”.
- existing `dashboard-ui/dist/index.html` is served at `/`.
- existing asset file is served.

- [ ] **Step 3: Run tests to verify failure**

Run: `py -m pytest tests/test_dashboard.py -q`

Expected: FAIL while split modules/static serving are absent.

- [ ] **Step 4: Move auth logic**

Move login request model, session cookie, bearer parsing, and auth dependency into `auth.py`. Preserve `HttpOnly` cookie behavior and Chinese errors.

- [ ] **Step 5: Move API logic**

Move status/memory/session/event/proactive/drift route registration into `api.py`, using a function such as:

```python
def register_dashboard_api(app, workspace, status, require_auth, plugin_manager=None):
    ...
```

- [ ] **Step 6: Add static serving**

Implement `static.py` to locate `dashboard-ui/dist` relative to repo/package root. If missing, serve a Chinese fallback page. If present, serve `index.html` for non-API routes and static assets under `/assets`.

- [ ] **Step 7: Shrink server composition**

`create_dashboard_app()` should compose auth, API, and static modules. Do not keep the old giant HTML/CSS/JS string after Vue static serving works.

- [ ] **Step 8: Run focused tests**

Run: `py -m pytest tests/test_dashboard.py -q`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add mini_agent/dashboard/auth.py mini_agent/dashboard/api.py mini_agent/dashboard/static.py mini_agent/dashboard/server.py tests/test_dashboard.py
git commit -m "拆分控制台后端并服务静态前端"
```

---

### Task 6: Plugin Dashboard API And Runtime Wiring

**Files:**
- Modify: `mini_agent/dashboard/api.py`
- Modify: `mini_agent/app.py`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_app_cli.py`

- [ ] **Step 1: Write failing standalone plugin API tests**

Create a workspace plugin and verify standalone Dashboard:
- `GET /api/plugins` returns builtin and workspace plugin records.
- workspace plugin is default disabled.
- `POST /api/plugins/workspace/demo/enable` returns `requires_restart=true`.
- state persists in SQLite.

- [ ] **Step 2: Write failing runtime plugin API tests**

Use a real `PluginManager` in TestClient:
- `GET /api/plugins` returns `mode="runtime"`.
- enable registers a tool immediately.
- disable unregisters it immediately.
- reload updates plugin code.

- [ ] **Step 3: Write failing AppRuntime injection test**

Patch `create_dashboard_app` and assert `plugin_manager` is `runtime.plugins` when Dashboard starts with Agent.

- [ ] **Step 4: Run tests to verify failure**

Run: `py -m pytest tests/test_dashboard.py tests/test_app_cli.py -q`

Expected: FAIL because plugin API and runtime injection are absent.

- [ ] **Step 5: Implement plugin API routes**

Add:

```text
GET  /api/plugins
POST /api/plugins/{source}/{name}/enable
POST /api/plugins/{source}/{name}/disable
POST /api/plugins/{source}/{name}/reload
```

All routes use the existing auth dependency. All user-visible messages are Chinese.

- [ ] **Step 6: Wire runtime plugin manager**

Update `AppRuntime._start_dashboard()`:

```python
dashboard_app = create_dashboard_app(..., plugin_manager=self.plugins)
```

- [ ] **Step 7: Run focused tests**

Run: `py -m pytest tests/test_dashboard.py tests/test_app_cli.py tests/test_plugins.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add mini_agent/dashboard/api.py mini_agent/app.py tests/test_dashboard.py tests/test_app_cli.py tests/test_plugins.py
git commit -m "增加控制台插件管理接口"
```

---

### Task 7: Vue Dashboard Scaffold And Build

**Files:**
- Create: `dashboard-ui/package.json`
- Create: `dashboard-ui/vite.config.ts`
- Create: `dashboard-ui/tsconfig.json`
- Create: `dashboard-ui/index.html`
- Create: `dashboard-ui/src/main.ts`
- Create: `dashboard-ui/src/App.vue`
- Create: `dashboard-ui/src/api/client.ts`
- Create: `dashboard-ui/src/api/types.ts`
- Create: `dashboard-ui/src/style.css`
- Modify: `.gitignore`

- [ ] **Step 1: Check Node/npm availability**

Run: `node --version` and `npm --version`

Expected: commands succeed. If not installed, stop and report the missing local prerequisite.

- [ ] **Step 2: Create minimal Vue/Vite module**

Use Vue 3 + Vite + TypeScript. Keep dependencies minimal:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@vitejs/plugin-vue": "...",
    "vite": "...",
    "typescript": "...",
    "vue": "...",
    "vue-tsc": "..."
  },
  "devDependencies": {}
}
```

Use actual current package versions generated by npm or pinned manually after install. Commit `package-lock.json`.

- [ ] **Step 3: Implement API client**

`client.ts` should use `credentials: "same-origin"`, parse JSON `detail`, and fallback to Chinese `请求失败（HTTP ${status}）`.

- [ ] **Step 4: Implement minimal app shell**

Render Chinese navigation and a status placeholder. Do not implement all views yet.

- [ ] **Step 5: Build**

Run:

```bash
cd dashboard-ui
npm install
npm run build
```

Expected: build succeeds and creates `dashboard-ui/dist`.

- [ ] **Step 6: Run Python static tests**

Run: `py -m pytest tests/test_dashboard.py -q`

Expected: PASS; static serving sees Vue dist.

- [ ] **Step 7: Commit**

```bash
git add .gitignore dashboard-ui package-lock.json tests/test_dashboard.py
git commit -m "创建Vue控制台前端模块"
```

---

### Task 8: Vue Views For Existing Dashboard Functions

**Files:**
- Create/Modify: `dashboard-ui/src/components/AppShell.vue`
- Create/Modify: `dashboard-ui/src/components/StatusBadge.vue`
- Create/Modify: `dashboard-ui/src/components/ConfirmDialog.vue`
- Create/Modify: `dashboard-ui/src/views/OverviewView.vue`
- Create/Modify: `dashboard-ui/src/views/MemoryView.vue`
- Create/Modify: `dashboard-ui/src/views/SessionsView.vue`
- Create/Modify: `dashboard-ui/src/views/EventsView.vue`
- Create/Modify: `dashboard-ui/src/views/ProactiveView.vue`
- Create/Modify: `dashboard-ui/src/views/DriftView.vue`
- Modify: `dashboard-ui/src/App.vue`
- Modify: `dashboard-ui/src/style.css`

- [ ] **Step 1: Implement app navigation state**

Use lightweight local state instead of adding Vue Router. Navigation labels: 总览、记忆、插件、会话、运行事件、主动推送、漂移任务.

- [ ] **Step 2: Implement overview/status**

Fetch `/api/status`, show workspace, running state, and refresh.

- [ ] **Step 3: Implement memory editor**

Recreate current memory behavior: file list, load, edit, dirty state, save, reload, Chinese errors, save backup message.

- [ ] **Step 4: Implement operational read-only views**

Sessions, events, proactive, and drift views fetch existing APIs and show compact Chinese lists.

- [ ] **Step 5: Build and inspect output**

Run:

```bash
cd dashboard-ui
npm run build
```

Expected: PASS.

- [ ] **Step 6: Run smoke server**

Start:

```bash
py -m mini_agent dashboard --workspace .tmp_workspace --host 127.0.0.1 --port 8791 --access-token secret
```

Verify login, navigation labels, memory view, and no visible English in primary UI. Stop the server after verification.

- [ ] **Step 7: Commit**

```bash
git add dashboard-ui
git commit -m "实现Vue控制台基础页面"
```

---

### Task 9: Vue Plugin Management View

**Files:**
- Create/Modify: `dashboard-ui/src/views/PluginsView.vue`
- Modify: `dashboard-ui/src/api/types.ts`
- Modify: `dashboard-ui/src/api/client.ts`
- Modify: `dashboard-ui/src/style.css`

- [ ] **Step 1: Implement plugin API types**

Add `PluginRecord`, `PluginListResponse`, and `PluginActionResponse` matching backend JSON.

- [ ] **Step 2: Implement plugin list**

Show total count, enabled count, failed count, mode label, plugin rows, source labels, status labels, tool/event counts, updated time, and error summary.

- [ ] **Step 3: Implement actions**

Enable, disable, reload buttons call backend routes. Disable asks confirmation. Runtime success and standalone restart-required messages are shown in Chinese.

- [ ] **Step 4: Handle locked and failed states**

Locked disable button is disabled with Chinese hint. Failed plugins show `last_error` summary.

- [ ] **Step 5: Build**

Run:

```bash
cd dashboard-ui
npm run build
```

Expected: PASS.

- [ ] **Step 6: Runtime smoke**

Run Dashboard with a test workspace plugin and verify plugin page can enable/disable/reload. Confirm the page says “已启用并立即生效” in runtime mode and “已保存，Agent 下次启动后生效” in standalone mode.

- [ ] **Step 7: Commit**

```bash
git add dashboard-ui
git commit -m "实现Vue插件管理页面"
```

---

### Task 10: Documentation And Final Verification

**Files:**
- Modify: `README.zh-CN.md`
- Modify: `README.md` if needed for command parity.
- Modify: `config.example.toml` only if configuration examples need comments.
- Test: all test suites.

- [ ] **Step 1: Update Chinese README**

Document:
- `dashboard-ui` development and build commands.
- Production still runs through Python Dashboard.
- Plugin management in Dashboard.
- Builtin plugins default enabled.
- Workspace plugins first discovered as disabled.
- Runtime vs standalone plugin operation behavior.

- [ ] **Step 2: Run backend tests**

Run: `py -m pytest -q`

Expected: all tests pass.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd dashboard-ui
npm run build
```

Expected: PASS.

- [ ] **Step 4: Run dry-runs**

Run:

```bash
py -m mini_agent run --dry-run --workspace .tmp_workspace --config config.toml
py -m mini_agent run --dry-run --workspace .tmp_workspace --config config.example.toml
```

Expected: both print `dry-run ok`.

- [ ] **Step 5: Run Dashboard HTTP smoke**

Start standalone Dashboard with token, login via `/api/login`, fetch `/`, verify Vue page contains Chinese title and no token leak. Stop server.

- [ ] **Step 6: Diff and sensitive checks**

Run:

```bash
git diff --check
git status --short
git ls-files config.toml .tmp_workspace
```

Expected: no diff-check output, local secrets are not tracked.

- [ ] **Step 7: Commit and push**

```bash
git add README.zh-CN.md README.md config.example.toml dashboard-ui mini_agent tests
git commit -m "实现Vue控制台和插件热插拔"
git push origin master
```

Expected: push succeeds and `git branch -vv` shows `master` at `origin/master`.

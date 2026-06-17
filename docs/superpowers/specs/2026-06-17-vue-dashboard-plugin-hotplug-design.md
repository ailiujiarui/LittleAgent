# Vue Dashboard 与插件热插拔设计

## 目标

把当前内嵌在 FastAPI 字符串里的 Dashboard 改造成独立 Vue 模块，同时让插件可以在
Dashboard 中查看、启用、禁用和重载。改造后的系统仍保持轻量：最终运行时仍是一个
Python Agent 进程；Vue 只作为构建后的静态资源由后端服务；插件热插拔只在同进程
Dashboard 中立即生效，不引入跨进程控制服务。

## 已确认决策

- Dashboard 前端使用 `dashboard-ui/` 独立 Vue + Vite + TypeScript 模块。
- 生产运行时，Python 后端直接服务 `dashboard-ui/dist`。
- 不引入大型 UI 组件库；第一版以原生 CSS 和少量组件完成中文运维界面。
- 插件启用状态存 SQLite，不写回 `config.toml`。
- Dashboard 同时管理内置插件和 workspace 插件。
- 内置插件首次默认启用，workspace 新插件首次默认禁用。
- 插件支持可选 `teardown(ctx)`，禁用和重载时调用。
- 随 Agent 启动的 Dashboard 支持真正热插拔；独立 Dashboard 只写状态并提示重启后生效。

## 模块边界

新增前端模块：

```text
dashboard-ui/
  package.json
  vite.config.ts
  src/
    api/
    components/
    views/
```

调整后端模块：

```text
mini_agent/dashboard/
  auth.py      # 登录、cookie、API 鉴权
  api.py       # 状态、记忆、会话、事件、插件管理 API
  static.py    # 挂载 Vue 构建产物，未构建时返回中文提示
  server.py    # create_dashboard_app() 组装 auth/api/static
```

插件能力留在插件模块中：

```text
mini_agent/plugins/
  manager.py   # discover/list/load/unload/reload
  state.py     # SQLite 插件启用状态和最近错误
  context.py   # PluginContext，记录插件注册的工具、事件和 teardown 上下文
```

Dashboard 不直接操作工具注册表和事件表，只调用 `PluginManager` 暴露的插件管理方法。

## 插件热插拔模型

`PluginManager` 维护三类信息：

- `discovered`: 当前能发现的内置插件和 workspace 插件。
- `active`: 当前进程已经加载的插件运行时对象。
- `states`: SQLite 中持久化的启用状态、锁定状态、最近错误和更新时间。

插件以 `(source, name)` 作为真实身份，展示时可显示 `name`，API 和持久化都不得只用
`name` 判断唯一性。第一版允许内置插件和 workspace 插件同名，但 Dashboard 会把它们
显示为不同来源的两条记录。前端可以把稳定 ID 表示为 `builtin:group_messages` 或
`workspace:my_plugin`。

每个已加载插件记录为 `PluginRuntime`：

```text
name
source: builtin / workspace
id: source:name
plugin_dir
module
setup
teardown?
registered_tools[]
subscribed_events[]
status: loaded / disabled / failed
last_error
```

为了支持卸载，需要补两个基础能力：

- `ToolRegistry` 保存工具来源 metadata，并提供
  `unregister_source(source_type="plugin", source_name=plugin_id)` 删除某插件注册的工具。
- `PluginContext.subscribe(...)` 记录 handler 属于哪个插件，禁用时可以移除该插件事件订阅。

`PluginContext.register_tool()` 需要把插件 ID 传给 `ToolRegistry.register()`，并同时把工具名
记录到当前 `PluginRuntime.registered_tools[]`。卸载时以来源 metadata 清理为主，
`registered_tools[]` 用于测试断言和错误排查。这样即使插件注册工具后 `setup()` 抛错，
系统也能清理本次 setup 已经写入的工具。

插件管理操作需要互斥。第一版使用 `PluginManager` 级别的 `asyncio.Lock` 串行化
`enable/disable/reload`，避免同一时间重复注册、卸载与加载交错或事件 handler 残留。
这个锁简单保守，符合轻量目标；如果以后插件数量和操作频率变高，再考虑插件级锁。

禁用流程：

1. SQLite 写入 `enabled=false`。
2. runtime 模式下：
   - 调用可选 `teardown(ctx)`。
   - 移除插件注册的工具。
   - 移除插件订阅的事件处理器。
   - 标记为 `disabled`。
3. standalone 模式下：
   - 只写 SQLite。
   - 返回 `requires_restart=true` 和中文提示。

启用流程：

1. SQLite 写入 `enabled=true`。
2. runtime 模式下：
   - 加载模块。
   - 创建临时 `PluginRuntime` 记录本次 setup 注册的工具和事件订阅。
   - 调用 `setup(ctx)`。
   - setup 成功后，把临时 runtime 放入 `active`。
   - 成功标记为 `loaded`，失败标记为 `failed` 并记录错误。
   - 如果 setup 失败，必须清理本次 setup 已注册的工具和事件订阅，再记录 `last_error`。
3. standalone 模式下：
   - 只写 SQLite。
   - 返回 `requires_restart=true` 和中文提示。

重载流程：

- runtime 模式：先 unload，再 load。
- standalone 模式：不执行代码，只返回 `requires_restart=true`。

边界规则：

- 插件报错不影响 Agent 主进程。
- `teardown` 报错只记录错误，不阻止工具和事件清理。
- `setup` 半失败时必须回滚本次已注册资源，不能残留可调用工具或事件 handler。
- 不强杀正在执行中的插件函数；禁用后不再接受新的工具调用和事件回调。
- 不做文件监听；用户在 Dashboard 点“重载”。
- 未来可通过 `locked=true` 标记系统必需插件，禁止关闭。

## Dashboard Vue 界面

第一版 Dashboard 是轻量中文运维面板：

```text
顶部栏：小助手控制台、运行状态、刷新
左侧导航：总览、记忆、插件、会话、运行事件、主动推送、漂移任务
主内容区：按导航显示对应页面
```

插件页显示：

- 插件名称。
- 来源：内置 / 工作区。
- 状态：已启用 / 已禁用 / 加载失败 / 需重启生效。
- 注册工具数量。
- 事件订阅数量。
- 最近错误摘要。
- 更新时间。
- 操作：启用、禁用、重载。

交互规则：

- 禁用插件前弹中文确认框。
- 加载失败只展示错误摘要，不在列表中塞长堆栈。
- runtime 模式操作成功显示“已启用并立即生效”等中文提示。
- standalone 模式操作成功显示“已保存，Agent 下次启动后生效”。
- locked 插件按钮禁用，提示“系统插件不可关闭”。

建议前端结构：

```text
dashboard-ui/src/
  api/client.ts
  api/types.ts
  components/AppShell.vue
  components/StatusBadge.vue
  components/ConfirmDialog.vue
  views/OverviewView.vue
  views/MemoryView.vue
  views/PluginsView.vue
  views/SessionsView.vue
  views/EventsView.vue
  views/ProactiveView.vue
  views/DriftView.vue
```

## API

保留现有接口：

```text
POST /api/login
GET  /api/status
GET  /api/memory/files
GET  /api/memory/files/{name}
POST /api/memory/files/{name}
GET  /api/sessions
GET  /api/sessions/{session_id}
GET  /api/events
GET  /api/proactive
GET  /api/drift
```

新增插件接口：

```text
GET  /api/plugins
POST /api/plugins/{source}/{name}/enable
POST /api/plugins/{source}/{name}/disable
POST /api/plugins/{source}/{name}/reload
```

`GET /api/plugins` 返回：

```json
{
  "mode": "runtime",
  "plugins": [
    {
      "name": "group_messages",
      "source": "builtin",
      "id": "builtin:group_messages",
      "enabled": true,
      "loaded": true,
      "locked": false,
      "tool_count": 1,
      "event_count": 1,
      "last_error": "",
      "updated_at": "2026-06-17T18:00:00+08:00",
      "requires_restart": false
    }
  ]
}
```

操作接口返回：

```json
{
  "ok": true,
  "plugin": {
    "name": "xiaohongshu_search",
    "source": "builtin",
    "id": "builtin:xiaohongshu_search",
    "enabled": true,
    "loaded": true,
    "last_error": ""
  },
  "requires_restart": false,
  "message": "已启用并立即生效"
}
```

`create_dashboard_app()` 增加可选参数：

```python
create_dashboard_app(
    workspace,
    status=None,
    access_token=None,
    plugin_manager=None,
)
```

- `plugin_manager is not None`: runtime 模式，插件操作立即生效。
- `plugin_manager is None`: standalone 模式，只修改 SQLite 状态。

`AppRuntime._start_dashboard()` 必须把 `self.plugins` 传给 `create_dashboard_app()`。
对应测试需要验证随 Agent 启动的 Dashboard 返回 `mode=runtime`，并且插件操作会立即改变
当前进程的工具注册表和事件订阅。

standalone 模式没有运行中的 `PluginManager`，但仍要能发现插件列表。后端需要提供一个轻量
`PluginCatalog`：

- 内置插件目录由 `AppRuntime` 当前注册的内置插件清单抽成共享函数，例如
  `build_builtin_plugin_specs(config)` 或不依赖运行时配置的 `builtin_plugin_specs()`。
- workspace 插件通过扫描 `workspace/plugins/*/plugin.py` 获得。
- 对于 `xiaohongshu_search` 这类 setup 依赖配置的内置插件，standalone 只展示插件元信息和
  SQLite 状态，不执行 setup。
- standalone 操作只更新 `plugin_states`，返回 `requires_restart=true`。

错误规则：

- 找不到插件：`404 插件不存在`。
- locked 插件禁用：`400 系统插件不可关闭`。
- 插件加载失败：HTTP 200，`loaded=false` 且 `last_error` 有值。
- 鉴权失败：`401 未授权`。

## 数据持久化

新增 SQLite 迁移，添加插件状态表：

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

不复用 `plugin_kv`。`plugin_kv` 是插件私有存储，`plugin_states` 是系统管理状态。

迁移落地规则：

- 新增 `mini_agent/db/migrations/002_plugin_states.sql`，不要修改 `001_init.sql`。
- 现有迁移器按文件名记录版本，新增迁移文件后旧数据库再次启动时会自动补建表。
- 测试需要覆盖：只执行过 `001_init` 的旧数据库再次运行迁移后存在 `plugin_states`，
  且 `schema_migrations` 记录 `002_plugin_states`。
- `updated_at` 在 `insert` 和 `update` 状态时都由写入逻辑显式设置为当前时间，
  不能依赖 SQLite 默认值在 update 时自动变化。

启动兼容策略：

- 内置插件没有状态记录时，默认 `enabled=true`。
- workspace 插件没有状态记录时，默认 `enabled=false`。
- 已有状态记录按 SQLite 加载。
- 第一版不显示已经不存在的插件状态记录，保持界面干净。

配置兼容：

- 不从 `config.toml` 管插件启停。
- 现有配置继续可用。
- 现有内置插件默认行为保持。
- workspace 插件行为会变化：首次发现默认禁用，需要在 Dashboard 中启用。
  README 需要明确说明这个安全边界。

## 安全与错误处理

- Dashboard 沿用现有访问令牌和 `HttpOnly` cookie 鉴权。
- 插件管理 API 全部需要鉴权。
- standalone 模式不能声称立即生效，必须返回 `requires_restart=true`。
- 插件异常只影响该插件状态，不影响 Agent 主循环。
- 前端所有用户可见错误使用中文兜底，不透出浏览器英文 `statusText`。

## 验证

后端测试：

- 插件状态默认值：内置启用，workspace 禁用。
- `enable/disable/reload` 在 runtime 模式立即生效。
- standalone 模式返回 `requires_restart=true`。
- 禁用插件后工具被反注册。
- 禁用插件后事件订阅被移除。
- `teardown` 被调用，且报错隔离。
- `setup` 注册部分工具后抛错时，本次工具和事件订阅被回滚。
- locked 插件不可禁用。
- 插件加载失败记录 `last_error`，不拖垮运行时。
- 同名内置插件和 workspace 插件状态互不覆盖。
- `reload` 后可以加载更新后的插件代码。
- runtime Dashboard 由 `AppRuntime._start_dashboard()` 注入 `self.plugins`，`/api/plugins`
  返回 `mode=runtime`。
- standalone Dashboard 能发现内置和 workspace 插件，但操作返回 `requires_restart=true`。
- 旧数据库迁移后创建 `plugin_states` 并记录 `002_plugin_states`。

前端测试：

- `npm run build` 通过。
- 插件页渲染中文状态、错误和操作按钮。
- 登录态 cookie 下请求 API 正常。
- Vue 构建产物缺失时，Python 后端返回中文提示，不返回英文 404。
- Vue 构建产物存在时，Python 后端能服务静态资源和前端入口。

集成验证：

- `py -m pytest -q`
- `npm run build`
- `py -m mini_agent dashboard ...` 能服务 Vue 构建产物。
- runtime 模式下启用/禁用插件后，工具注册表和事件订阅立即变化。

## 非目标

- 不做跨进程 Agent 控制协议。
- 不做插件独立进程隔离。
- 不做插件文件自动监听。
- 不做多用户 Dashboard 权限系统。
- 不做大型 UI 组件库或复杂国际化系统。

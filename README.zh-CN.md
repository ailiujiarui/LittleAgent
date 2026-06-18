# LittleAgent 中文说明

[English](README.md) | 中文

LittleAgent 是一个面向 QQ 场景的轻量级 Agent 项目。它直接接入
OneBot v11 / NapCat，使用 OpenAI 兼容接口调用大模型，并把会话处理、
工具调用、插件扩展、记忆存储、MCP 工具导入和 Dashboard API 放在一个
小而清晰的 Python 项目里。

这个项目的重点不是堆功能，而是让 QQ 机器人具备可理解、可测试、可扩展
的 Agent 骨架。你可以把它当作个人 QQ 助手的基础，也可以把它作为二次
开发自己的聊天 Agent、插件系统或工具调用实验项目的起点。

## 核心优势

### 面向 QQ 场景，不绕远路

LittleAgent 使用 OneBot v11 作为 QQ 入口，适合配合 NapCat 的反向
WebSocket 使用。项目内已经包含 QQ 私聊、群聊、群回复和消息发送的核心
通路，不需要先搭一套额外的 Web 服务再转发消息。

### 小型架构，容易读懂和修改

项目主体是普通 Python 模块：`app` 负责运行时装配，`channels` 负责
OneBot QQ 接入，`agent_loop` 负责会话队列，`tools` 负责工具注册与执行，
`plugins` 负责扩展机制，`memory` 和 `db` 负责记忆与 SQLite 存储。

这让开发者可以很快定位问题，也可以只改一个边界清晰的模块，而不用先理解
一整套复杂框架。

### 会话隔离和并发处理

同一个会话内的消息按顺序处理，避免同一个用户或同一个群的多条消息互相
打乱；不同会话可以并发处理，提高多用户场景下的响应能力。这一点在测试中
有明确覆盖。

### OpenAI 兼容模型接口

默认配置面向 DeepSeek 的 OpenAI 兼容 Chat API，但代码使用的是通用的
OpenAI-compatible 请求格式。只要服务端兼容 `/chat/completions` 风格的
接口，就可以通过配置切换 `base_url`、`api_key` 和 `model`。

### 结构化工具调用

工具由 Pydantic 参数模型定义，自动生成工具 schema，并在执行前做参数
校验。LLM 可以调用内置工具、插件工具和 MCP 导入的工具；工具错误会作为
结构化结果返回给模型，而不是直接打断整个会话。

### 插件系统足够轻，扩展成本低

插件只需要放在 workspace 的 `plugins/<name>/plugin.py` 中并提供
`setup(ctx)`。插件可以注册工具、订阅事件，也可以使用插件 KV 存储持久化
自己的状态。一个插件失败不会阻止其他插件或主程序启动。

### 群消息可读，但不刷屏

LittleAgent 支持配置群聊后静默归档普通群消息，再通过
`read_group_messages` 工具按需读取最近上下文。`require_at = true` 时，
普通群消息只会被记录，不会触发 LLM 回复；只有 `@机器人` 的群消息才会
进入回复链路。

这让机器人能理解群里的近期上下文，同时避免因为监听群聊而自动刷屏。

### 记忆既可读又可查

项目同时使用 Markdown 文件和 SQLite。Markdown 文件适合人工检查与编辑，
SQLite 适合会话、插件 KV、记忆条目和运行记录等结构化数据。记忆相关工具
支持读取、写入、搜索和合并待处理记忆。

### 可接入 MCP 工具

项目包含 stdio MCP 客户端和工具包装层，可以把 MCP server 暴露的工具
导入到 Agent 的工具注册表中。失败的 MCP server 会被隔离，不会拖垮其他
工具。

### 有测试覆盖，适合持续改造

仓库包含覆盖配置加载、数据库迁移、OneBot 通道、会话队列、工具注册、
插件系统、记忆、MCP、Dashboard、主动推送和 Drift 模块的 pytest 测试。
这使得项目适合在功能继续增长时保持行为可验证。

## 能力总览

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| QQ 私聊接入 | 已接入运行时 | 通过 OneBot v11 事件进入 AgentLoop |
| QQ 群聊回复 | 已接入运行时 | 支持配置群、发送者白名单和 `require_at` |
| 群消息读取插件 | 已接入运行时 | 在线期间归档配置群消息，工具按需读取 |
| OpenAI 兼容 LLM | 已接入运行时 | 支持 tool calls 和文本回复 |
| 工具注册表 | 已接入运行时 | 支持 schema 生成、参数校验、上下文注入 |
| 插件系统 | 已接入运行时 | 支持 workspace 插件、内置插件和 Dashboard 启停 |
| 小红书搜索插件 | 已接入运行时 | 默认调用 xiaohongshu-mcp，最新在前返回链接 |
| Markdown/SQLite 记忆 | 已接入运行时 | 支持读写、搜索和合并待处理记忆 |
| stdio MCP 导入 | 已接入运行时 | 支持列出和调用 MCP server 工具 |
| Dashboard UI/API | 已接入运行时 | Vue 静态前端由 Python 服务，可独立启动或随 Agent 后台启动 |
| 主动推送模块 | 已接入运行时 | 支持 RSS / HTTP JSON 数据源、阈值、冷却和每日上限 |
| Drift 模块 | 已接入运行时 | 可配置为后台任务，复用安全约束和运行记录逻辑 |

## 简化架构

```text
NapCat / OneBot v11
        |
        v
OneBotQQChannel
        |
        +--> PluginManager.emit("group_message") --> group_messages plugin
        |
        v
MessageBus
        |
        v
AgentLoop / SessionWorker
        |
        v
PassiveTurnPipeline
        |
        +--> OpenAI-compatible LLM
        +--> ToolRegistry
                |
                +--> built-in tools
                +--> plugin tools
                +--> MCP tools
```

## 环境要求

- Python 3.9 或更高版本
- 一个 OpenAI 兼容的大模型服务
- 如需 QQ 接入，需要 NapCat 或其他 OneBot v11 兼容实现

安装依赖：

```bash
py -m pip install -e .
```

运行测试：

```bash
py -m pytest
```

## 快速开始

初始化 workspace：

```bash
py -m mini_agent init --workspace workspace
```

创建配置文件时，建议从示例配置复制，并使用环境变量保存密钥：

```toml
workspace = "workspace"

[llm]
base_url = "https://api.deepseek.com"
api_key = "${DEEPSEEK_API_KEY}"
model = "deepseek-v4-flash"

[onebot]
host = "127.0.0.1"
port = 8765
path = "/onebot/v11/ws"
bot_uin = "123456789"
allow_private = []

[onebot.groups."222222222"]
allow_from = []
require_at = true
```

设置环境变量：

```powershell
$env:DEEPSEEK_API_KEY="your-api-key"
```

检查配置和工具注册：

```bash
py -m mini_agent run --dry-run --workspace workspace --config config.toml
```

启动 Agent：

```bash
py -m mini_agent run --workspace workspace --config config.toml
```

## QQ / NapCat 接入

在 NapCat 中配置反向 WebSocket：

```text
ws://127.0.0.1:8765/onebot/v11/ws
```

如果 Agent 运行在宿主机，而 NapCat 运行在 Docker 容器中，通常需要把地址
改成宿主机可访问的形式，例如：

```text
ws://host.docker.internal:8765/onebot/v11/ws
```

可以用命令查看当前 OneBot 配置：

```bash
py -m mini_agent qq-check --config config.toml
```

群聊配置示例：

```toml
[onebot.groups."222222222"]
allow_from = []
require_at = true
```

- `allow_from = []` 表示不限制群内发送者。
- `require_at = true` 表示只有 `@机器人` 的群消息才会触发回复。
- 普通群消息仍可被群消息插件归档，但不会自动回复。

## 群消息读取插件

内置 `group_messages` 插件会监听已配置群的消息，并把最近消息保存在插件
KV 存储中。它注册的工具名是：

```text
read_group_messages
```

在群聊上下文中，可以省略 `group_id`：

```json
{"limit": 20}
```

在私聊或其他上下文中，需要显式指定群号：

```json
{"group_id": "222222222", "limit": 20}
```

行为边界：

- 只归档 `[onebot.groups]` 中配置过的群。
- 遵守群配置里的 `allow_from`。
- 只记录机器人在线期间收到的消息。
- 每个群最多保留最近 200 条。
- 单次工具调用最多返回 100 条。
- 不从 NapCat 拉取离线历史。

## 小红书搜索插件

内置 `xiaohongshu_search` 插件会注册工具：

```text
search_xiaohongshu_posts
```

它不直接破解或爬取小红书站内接口。默认情况下，插件通过 HTTP MCP 调用
本机 `xiaohongshu-mcp` 的 `search_feeds` 工具；如果你有自己的搜索适配器，
也可以把 endpoint 配成兼容的 HTTP JSON 服务。

默认配置：

```toml
[xiaohongshu]
search_endpoint = "http://localhost:18060/mcp"
```

首次使用 `xiaohongshu-mcp` 需要启动服务并完成小红书扫码登录。登录状态保存在
`docker/xiaohongshu-mcp/data/`，该目录不要提交到仓库。

兼容的 HTTP JSON 服务可以返回数组，也可以返回带 `items` 字段的对象。配置
`search_api_key` 后，插件会以 Bearer token 形式传给搜索服务：

```toml
[xiaohongshu]
search_endpoint = "https://your-search-service.example/search"
search_api_key = "your-optional-api-key"
```

```json
{
  "items": [
    {
      "title": "上海安静咖啡馆",
      "url": "https://www.xiaohongshu.com/explore/example",
      "published_at": "2026-06-13T10:30:00+08:00",
      "summary": "适合工作，有插座"
    }
  ]
}
```

字段别名支持：

- 标题：`title` 或 `desc`
- 链接：`url`、`link` 或 `share_link`
- 时间：`published_at`、`time`、`timestamp`、`create_time` 或 `date`
- 内容：`content`、`summary`、`desc` 或 `text`

工具调用示例：

```json
{
  "query": "上海 咖啡",
  "require_keywords": ["安静", "插座"],
  "exclude_keywords": ["广告"],
  "limit": 10
}
```

返回结果会：

- 跳过没有链接的条目。
- 要求 `require_keywords` 全部命中标题或正文。
- 排除命中 `exclude_keywords` 的条目。
- 按发布时间最新在前排序。
- 以“日期 标题 链接”的多行文本返回，适合直接发到 QQ。

## 插件开发

插件目录结构：

```text
workspace/
  plugins/
    echo_plugin/
      plugin.py
```

最小插件示例：

```python
from pydantic import BaseModel

from mini_agent.tools.base import Tool


class EchoArgs(BaseModel):
    text: str


async def echo(args):
    return {"text": args.text}


def setup(ctx):
    ctx.register_tool(Tool("plugin_echo", "Echo text.", EchoArgs, echo))
```

插件也可以订阅事件：

```python
def setup(ctx):
    async def on_group_message(event):
        ctx.kv_set("last_group_message", event)

    ctx.subscribe("group_message", on_group_message)
```

插件启用状态保存在 workspace 的 SQLite 数据库里，不写回 `config.toml`。内置插件首次发现时默认启用；
workspace 插件首次发现时默认禁用，需要在 Dashboard 的“插件”页面启用。这样可以避免把新放进去的
实验插件自动加入运行时。

插件可以提供可选的清理函数：

```python
def teardown(ctx):
    ctx.kv_set("last_shutdown", "done")
```

当 Dashboard 在随 Agent 启动的运行时模式中禁用或重载插件时，会调用 `teardown(ctx)`，并移除该插件注册
的工具和事件订阅。独立 Dashboard 没有运行中的 Agent 进程，只会保存启用状态，并提示下次 Agent 启动后生效。

## MCP 工具导入

workspace 中的 `mcp_servers.json` 用于配置 stdio MCP server。启动运行时后，
项目会把 MCP server 暴露的工具包装进 `ToolRegistry`。也可以使用：

```bash
py -m mini_agent mcp-list --workspace workspace
```

查看已连接的 MCP server 和工具。

## Dashboard

Dashboard 是一个中文控制台，前端位于独立的 `dashboard-ui/` Vue + Vite 模块中，构建后由 Python 后端
作为静态资源服务。可以在浏览器里查看运行状态、列出 workspace 记忆文件、
编辑记忆文件并在保存前自动生成备份。页面也会只读展示最近会话、运行事件、主动推送
记录和 Drift 运行记录，并可配置启用、禁用和重载插件。

前端开发和构建：

```bash
cd dashboard-ui
npm install
npm run build
```

生产运行仍然通过 Python Dashboard 入口启动；`dashboard-ui/dist` 不提交到仓库。如果没有先构建前端，
Dashboard 会返回中文提示页，提醒执行 `npm run build`。

单独启动控制台：

```bash
py -m mini_agent dashboard --workspace workspace --host 127.0.0.1 --port 8787 --access-token your-dashboard-token
```

打开浏览器访问：

```text
http://127.0.0.1:8787
```

如果设置了访问令牌，页面会先显示中文登录页；输入 `--access-token` 对应的令牌后进入控制台。
登录成功后，服务端会写入一个 `HttpOnly` 会话 cookie；令牌不会出现在页面源码或浏览器地址栏里。

Dashboard 对可读写的记忆文件做了白名单限制，并在写入前生成备份。也可以
直接使用 `/api/status`、`/api/memory/files`、`/api/sessions`、`/api/events`、
`/api/proactive`、`/api/drift` 和 `/api/plugins` 等 API 做自动化检查。配置访问令牌后，API 需要带上：

```text
Authorization: Bearer your-dashboard-token
```

如果希望 Dashboard 随 Agent 一起启动，可以在配置中启用。建议令牌使用环境变量：

```toml
[dashboard]
enabled = true
host = "127.0.0.1"
port = 8787
access_token = "${DASHBOARD_ACCESS_TOKEN}"
```

插件页面有两种模式：

- 随 Agent 启动的 Dashboard 是运行时模式，启用、禁用和重载会立即影响当前进程的工具注册和事件订阅。
- 单独启动的 Dashboard 是独立模式，只修改 SQLite 中的插件状态，并提示 Agent 下次启动后生效。

插件列表会区分“内置”和“工作区”来源；内置插件默认启用，workspace 插件默认禁用。被锁定的系统插件不能关闭。

## 主动推送和 Drift

主动推送可以配置 RSS 或 HTTP JSON 数据源。后台循环会拉取数据源、让模型判断
是否值得推送，并通过 `message_push` 发到目标 QQ 会话：

```toml
[proactive]
enabled = true
target_channel = "qq"
target_chat_id = "123456789"
threshold = 0.65
cooldown_minutes = 30
daily_max_pushes = 8

[[proactive.sources]]
type = "rss"
name = "agent-news"
url = "https://example.test/feed.xml"

[[proactive.sources]]
type = "http_json"
name = "alerts"
url = "https://example.test/alerts.json"
```

HTTP JSON 数据源可以返回数组，也可以返回带 `items` 字段的对象；每个条目建议
包含 `id` 或 `url`、`title`、`summary` 或 `content`。Drift 可以通过配置打开，
它会扫描 `workspace/drift/skills/*.md`，按最少运行优先的顺序执行技能：

```toml
[drift]
enabled = true
min_interval_minutes = 120
max_steps = 8
```

## 安全建议

- 不要把真实 API key 写进仓库。
- 使用 `${DEEPSEEK_API_KEY}` 这类环境变量占位符。
- 不要提交 `config.toml`。
- 不要提交 `workspace/`，里面可能包含记忆、插件 KV 和会话数据库。
- 不要提交 NapCat 的二维码、QQ 登录态、消息数据库和日志。
- Dashboard 如果绑定到非本机地址，必须设置 `dashboard.access_token`，并避免把令牌写入仓库。
- 群消息归档会保存群消息文本，请只在你有权限的群里启用。
- 如果密钥曾经暴露，应该立即去服务商后台轮换密钥。

项目 `.gitignore` 已默认忽略本地配置、workspace、日志、数据库和 NapCat
运行态目录。

## 测试

运行全量测试：

```bash
py -m pytest
```

当前测试覆盖的重点包括：

- 配置加载和环境变量展开
- SQLite 迁移幂等性
- OneBot 私聊和群聊事件解析
- 群消息归档但不触发回复
- 会话 FIFO 和跨会话并发
- 工具 schema、参数校验和上下文注入
- 插件加载、事件订阅和插件隔离
- 记忆读写、搜索和合并
- MCP server 连接、工具导入和失败隔离
- Dashboard 记忆文件读写白名单和运行数据 API
- 主动推送和 Drift 后台任务的关键约束

## 当前边界

- 群消息读取只覆盖机器人在线期间收到的消息。
- 主动推送只有在配置数据源后才会产生候选内容；没有数据源时后台循环会空跑。
- Drift 只会执行 `workspace/drift/skills/*.md` 中的本地技能文件。
- Dashboard 有单令牌访问保护，但还没有多用户、角色权限和登录审计系统。
- 目前没有多实例分布式协调。
- QQ 接入依赖 NapCat 或其他 OneBot v11 兼容实现的稳定性。

## 项目结构

```text
mini_agent/
  app.py                 # 运行时装配
  __main__.py            # Typer CLI
  agent_loop.py          # 会话队列和消息处理
  passive_turn.py        # 单轮 LLM + 工具调用流程
  channels/onebot_qq.py  # OneBot v11 QQ 接入
  tools/                 # 工具定义、注册表和消息推送
  plugins/               # 插件上下文、管理器和内置插件
  memory/                # Markdown/SQLite 记忆
  mcp/                   # stdio MCP 客户端和工具包装
  proactive/             # 主动推送相关模块
  drift/                 # Drift 技能运行模块
  dashboard/             # FastAPI Dashboard API
  db/                    # SQLite 迁移和存储
dashboard-ui/             # Vue Dashboard 前端模块
tests/                   # pytest 测试
```

## 适合谁

LittleAgent 适合想要一个“能跑、能读、能改”的 QQ Agent 骨架的开发者：

- 你想快速接入 QQ 私聊和群聊。
- 你想让机器人能调用工具，而不是只做文本补全。
- 你想通过插件逐步扩展能力。
- 你希望记忆和运行数据能被检查、备份和测试。
- 你希望代码量保持在可理解范围内，方便二次开发。

## 开源许可证

LittleAgent 使用
[GNU Affero General Public License v3.0 only](LICENSE)
（`AGPL-3.0-only`）开源。

这是强 copyleft 许可证。除常规分发义务外，如果你修改本项目并通过网络向
用户提供服务，还需要按照许可证要求向这些用户提供对应版本的完整源码。
二次分发、修改和网络部署前，请阅读 [LICENSE](LICENSE) 全文并确保满足其
条款。
## xiaohongshu-mcp 部署脚本

仓库提供本地 Docker 部署脚本，默认服务地址为
`http://localhost:18060/mcp`：

```powershell
cd docker/xiaohongshu-mcp
Copy-Item docker-compose.example.yml docker-compose.yml
.\start.ps1
.\status.ps1
```

首次使用需要先完成小红书扫码登录。登录状态会保存在
`docker/xiaohongshu-mcp/data/`，不要删除或提交这个目录，否则需要重新登录。
如果服务部署在其他地址，可通过 `[xiaohongshu]` 覆盖 endpoint：

```toml
[xiaohongshu]
search_endpoint = "http://localhost:18060/mcp"
```

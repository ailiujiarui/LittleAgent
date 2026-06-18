# Mini Agent

[中文说明](README.zh-CN.md)

Minimal Akashic-inspired agent with direct OneBot v11 QQ entry, session workers,
OpenAI-compatible tool calling, Markdown/SQLite memory, plugins, proactive push,
Drift, a Vue dashboard served by Python, and stdio MCP tool import.

## Quick Start

```bash
py -m mini_agent init --workspace workspace
py -m mini_agent run --dry-run --workspace workspace
```

## Dashboard

The dashboard frontend lives in `dashboard-ui/` and is served as static files by
the Python FastAPI dashboard after build:

```bash
cd dashboard-ui
npm install
npm run build
```

The dashboard can run standalone or with the agent. In runtime mode it can enable,
disable, and reload plugins immediately; in standalone mode it only updates the
SQLite plugin state for the next agent start.

## DeepSeek

The default LLM provider is DeepSeek's OpenAI-compatible chat API.

```toml
[llm]
base_url = "https://api.deepseek.com"
api_key = "${DEEPSEEK_API_KEY}"
model = "deepseek-v4-flash"
```

Set the API key before running:

```powershell
$env:DEEPSEEK_API_KEY="your-api-key"
```

For QQ, configure NapCat reverse WebSocket to:

```text
ws://127.0.0.1:8765/onebot/v11/ws
```

Then run:

```bash
py -m mini_agent run --workspace workspace --config config.toml
```

## License

LittleAgent is licensed under the
[GNU Affero General Public License v3.0 only](LICENSE) (`AGPL-3.0-only`).
If you modify the software and make it available to users over a network, you
must offer those users the corresponding source code as required by the
license.

# Mini Agent

Minimal Akashic-inspired agent with direct OneBot v11 QQ entry, session workers,
OpenAI-compatible tool calling, Markdown/SQLite memory, plugins, proactive push,
Drift, dashboard APIs, and stdio MCP tool import.

## Quick Start

```bash
py -m mini_agent init --workspace workspace
py -m mini_agent run --dry-run --workspace workspace
```

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

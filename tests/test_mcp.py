import asyncio
import json
import sys
import textwrap


def _write_fake_mcp_server(path):
    path.write_text(
        textwrap.dedent(
            """
            import json
            import sys

            for line in sys.stdin:
                request = json.loads(line)
                method = request.get("method")
                if method == "initialize":
                    result = {"serverInfo": {"name": "fake"}}
                elif method == "tools/list":
                    result = {
                        "tools": [
                            {
                                "name": "echo",
                                "description": "Echo text",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"text": {"type": "string"}},
                                    "required": ["text"],
                                },
                            }
                        ]
                    }
                elif method == "tools/call":
                    text = request["params"]["arguments"]["text"]
                    result = {"content": [{"type": "text", "text": "echo: " + text}]}
                else:
                    result = {}
                print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
            """
        ),
        encoding="utf-8",
    )


def test_stdio_mcp_handshake_registers_wrapper_and_calls_tool(tmp_path):
    from mini_agent.mcp.registry import McpRegistry
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        server = tmp_path / "fake_mcp.py"
        _write_fake_mcp_server(server)
        config = tmp_path / "mcp_servers.json"
        config.write_text(
            json.dumps(
                {
                    "echo_server": {
                        "command": [sys.executable, str(server)],
                        "cwd": str(tmp_path),
                    }
                }
            ),
            encoding="utf-8",
        )

        tools = ToolRegistry()
        registry = McpRegistry(config_path=config, tools=tools, timeout=3)
        await registry.connect_all()
        result = await tools.execute("mcp__echo_server__echo", {"text": "hi"})
        listed = await tools.execute("mcp_list", {})
        await registry.close_all()

        assert result.success is True
        assert result.text == "echo: hi"
        assert listed.content["servers"] == {"echo_server": ["echo"]}

    asyncio.run(scenario())


def test_failed_mcp_server_isolated(tmp_path):
    from mini_agent.mcp.registry import McpRegistry
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        config = tmp_path / "mcp_servers.json"
        config.write_text(
            json.dumps({"bad": {"command": [sys.executable, "missing_server.py"]}}),
            encoding="utf-8",
        )

        tools = ToolRegistry()
        registry = McpRegistry(config_path=config, tools=tools, timeout=1)
        await registry.connect_all()
        listed = await tools.execute("mcp_list", {})
        await registry.close_all()

        assert "bad" in registry.failed
        assert listed.content["servers"] == {}

    asyncio.run(scenario())

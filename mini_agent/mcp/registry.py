import json
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel

from mini_agent.mcp.client import StdioMCPClient
from mini_agent.mcp.tool import MCPTool
from mini_agent.tools.base import Tool
from mini_agent.tools.registry import ToolRegistry


class NoArgs(BaseModel):
    pass


class McpRegistry:
    def __init__(
        self,
        config_path: Path,
        tools: ToolRegistry,
        timeout: float = 5.0,
    ) -> None:
        self.config_path = Path(config_path)
        self.tools = tools
        self.timeout = timeout
        self.clients: Dict[str, StdioMCPClient] = {}
        self.server_tools: Dict[str, List[str]] = {}
        self.failed: Dict[str, str] = {}
        self._register_list_tool()

    async def connect_all(self) -> None:
        for name, config in self._load_config().items():
            try:
                client = StdioMCPClient(
                    name=name,
                    command=list(config["command"]),
                    cwd=Path(config["cwd"]) if config.get("cwd") else None,
                    timeout=self.timeout,
                )
                tool_infos = await client.connect()
            except Exception as exc:  # noqa: BLE001 - isolate broken MCP servers.
                self.failed[name] = str(exc)
                continue

            self.clients[name] = client
            self.server_tools[name] = [info.name for info in tool_infos]
            for info in tool_infos:
                self.tools.register(
                    MCPTool(name, info, client),
                    source_type="mcp",
                    source_name=name,
                )

    async def close_all(self) -> None:
        for client in list(self.clients.values()):
            await client.close()
        self.clients.clear()

    def _load_config(self):
        if not self.config_path.exists():
            return {}
        return json.loads(self.config_path.read_text(encoding="utf-8") or "{}")

    def _register_list_tool(self) -> None:
        async def mcp_list(args: NoArgs):
            return {"servers": self.server_tools}

        self.tools.register(Tool("mcp_list", "List connected MCP servers and tools.", NoArgs, mcp_list))

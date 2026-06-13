from typing import Any, Dict

from mini_agent.mcp.client import McpToolInfo, StdioMCPClient
from mini_agent.tools.base import ToolResult


class MCPTool:
    def __init__(self, server_name: str, info: McpToolInfo, client: StdioMCPClient) -> None:
        self.server_name = server_name
        self.remote_name = info.name
        self.name = f"mcp__{server_name}__{info.name}"
        self.description = info.description
        self.input_schema = info.input_schema or {"type": "object", "properties": {}}
        self.client = client

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    async def execute(self, arguments: Dict[str, Any], context=None) -> ToolResult:
        try:
            result = await self.client.call(self.remote_name, arguments)
        except Exception as exc:  # noqa: BLE001 - MCP failures are tool results.
            return ToolResult(success=False, error=str(exc))

        content = result.get("content", [])
        text_parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "\n".join(part for part in text_parts if part)
        return ToolResult(
            success=True,
            content={"content": content},
            text=text,
            content_blocks=content if isinstance(content, list) else [],
        )

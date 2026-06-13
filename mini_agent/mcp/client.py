import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class McpToolInfo(BaseModel):
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)


class StdioMCPClient:
    def __init__(
        self,
        name: str,
        command: List[str],
        cwd: Optional[Path] = None,
        timeout: float = 5.0,
    ) -> None:
        self.name = name
        self.command = command
        self.cwd = Path(cwd) if cwd else None
        self.timeout = timeout
        self.process: Optional[asyncio.subprocess.Process] = None
        self._next_id = 0

    async def connect(self) -> List[McpToolInfo]:
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=str(self.cwd) if self.cwd else None,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await self._request("initialize", {})
        tools_result = await self._request("tools/list", {})
        return [
            McpToolInfo(
                name=tool["name"],
                description=tool.get("description", ""),
                input_schema=tool.get("inputSchema") or {"type": "object", "properties": {}},
            )
            for tool in tools_result.get("tools", [])
        ]

    async def call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )

    async def close(self) -> None:
        if self.process is None:
            return
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=1)
            except asyncio.TimeoutError:
                self.process.kill()
        self.process = None

    async def _request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("MCP client is not connected")
        self._next_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params,
        }
        self.process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
        await self.process.stdin.drain()
        raw_line = await asyncio.wait_for(self.process.stdout.readline(), timeout=self.timeout)
        if not raw_line:
            raise RuntimeError(f"MCP server {self.name} closed stdout")
        response = json.loads(raw_line.decode("utf-8"))
        if "error" in response:
            raise RuntimeError(str(response["error"]))
        return response.get("result", {})

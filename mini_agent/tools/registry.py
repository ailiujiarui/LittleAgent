from typing import Any, Dict, List, Optional, Sequence

from mini_agent.tools.base import Tool, ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}
        self._context: Dict[str, Any] = {}

    def register(self, tool: Tool, **metadata: Any) -> None:
        self._tools[tool.name] = tool

    def set_context(self, context: Dict[str, Any]) -> None:
        self._context = dict(context)

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def get_tool(self, name: str) -> Optional[Tool]:
        return self.get(name)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> List[str]:
        return sorted(self._tools)

    def get_registered_names(self) -> List[str]:
        return self.names()

    def list_schemas(self, names: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
        return self.get_schemas(names=names)

    def get_schemas(self, names: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
        selected_names = list(names) if names is not None else self.names()
        return [
            self._tools[name].schema()
            for name in selected_names
            if name in self._tools
        ]

    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(success=False, error=f"unknown tool: {name}")
        merged_context = {**self._context, **(context or {})}
        merged_arguments = {**merged_context, **arguments}
        return await tool.execute(merged_arguments, context=merged_context)

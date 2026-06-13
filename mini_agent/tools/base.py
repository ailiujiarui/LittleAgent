import inspect
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel, Field, ValidationError


class ToolResult(BaseModel):
    success: bool
    content: Dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    text: str = ""
    content_blocks: List[Dict[str, Any]] = Field(default_factory=list)


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        args_model: Type[BaseModel],
        handler: Callable[..., Any],
        inject_context: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self.args_model = args_model
        self.handler = handler
        self.inject_context = inject_context

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        try:
            args = self.args_model.model_validate(arguments)
        except ValidationError as exc:
            return ToolResult(success=False, error=f"validation error: {exc}")

        try:
            if self.inject_context:
                value = self.handler(args, context or {})
            else:
                value = self.handler(args)
            if inspect.isawaitable(value):
                value = await value
        except Exception as exc:  # noqa: BLE001 - tool errors are returned to the model.
            return ToolResult(success=False, error=str(exc))

        if isinstance(value, ToolResult):
            return value
        if isinstance(value, str):
            return ToolResult(success=True, content={"result": value}, text=value)
        if isinstance(value, dict):
            return ToolResult(success=True, content=value)
        return ToolResult(success=True, content={"result": value})

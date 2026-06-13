import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str = ""
    tool_calls: List[ToolCall] = Field(default_factory=list)


class OpenAICompatibleLLM:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> LLMResponse:
        try:
            import httpx
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard.
            raise RuntimeError("httpx is required for OpenAICompatibleLLM") from exc

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return normalize_openai_response(response.json())


def normalize_openai_response(data: Dict[str, Any]) -> LLMResponse:
    message = data["choices"][0]["message"]
    tool_calls = []
    for call in message.get("tool_calls") or []:
        function = call.get("function", {})
        raw_arguments = function.get("arguments") or "{}"
        if isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {"_raw": raw_arguments}
        else:
            arguments = raw_arguments
        tool_calls.append(
            ToolCall(
                id=str(call.get("id", "")),
                name=str(function.get("name", "")),
                arguments=arguments,
            )
        )
    return LLMResponse(content=message.get("content") or "", tool_calls=tool_calls)

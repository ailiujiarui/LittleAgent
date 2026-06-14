import json
from typing import Any, Dict, List, Optional

from mini_agent.db.stores import MessageStore
from mini_agent.llm import LLMResponse, ToolCall
from mini_agent.models import InboundMessage
from mini_agent.tools.registry import ToolRegistry


class PassiveTurnPipeline:
    def __init__(
        self,
        llm: Optional[Any] = None,
        tools: Optional[ToolRegistry] = None,
        message_store: Optional[MessageStore] = None,
        system_prompt: str = "You are a helpful QQ agent.",
        max_tool_iterations: int = 6,
    ) -> None:
        self.llm = llm
        self.tools = tools or ToolRegistry()
        self.message_store = message_store
        self.system_prompt = system_prompt
        self.max_tool_iterations = max_tool_iterations

    async def run(self, message: InboundMessage) -> str:
        if self.llm is None:
            raise NotImplementedError("passive turn pipeline is not configured")

        session_key = message.session_key
        if self.message_store is not None:
            self.message_store.add_message(session_key, "user", message.text)

        chat_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": message.text},
        ]
        context = {
            "session_key": session_key,
            "channel": message.channel,
            "chat_id": message.chat_id,
            "sender_id": message.sender_id,
        }

        for _ in range(self.max_tool_iterations):
            response = await self.llm.chat(chat_messages, self.tools.get_schemas())
            if not response.tool_calls:
                return self._finish(session_key, response.content)

            chat_messages.append(_assistant_tool_call_message(response))
            for tool_call in response.tool_calls:
                result = await self.tools.execute(
                    tool_call.name,
                    tool_call.arguments,
                    context=context,
                )
                if not result.success:
                    return self._finish(
                        session_key,
                        _user_visible_tool_error(tool_call.name, result.error),
                    )
                chat_messages.append(_tool_result_message(tool_call, result.model_dump()))

        return self._finish(session_key, "Tool iteration limit reached.")

    def _finish(self, session_key: str, content: str) -> str:
        if self.message_store is not None:
            self.message_store.add_message(session_key, "assistant", content)
        return content


def _assistant_tool_call_message(response: LLMResponse) -> Dict[str, Any]:
    return {
        "role": "assistant",
        "content": response.content or "",
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in response.tool_calls
        ],
    }


def _tool_result_message(tool_call: ToolCall, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }


def _user_visible_tool_error(tool_name: str, error: str) -> str:
    if "XHS_SEARCH_ENDPOINT" in error or "xiaohongshu-mcp" in error:
        return (
            "工具调用失败：小红书搜索数据源不可用。"
            "请先启动并登录 xiaohongshu-mcp，确认 http://localhost:18060/mcp 可访问；"
            "如果服务不在本机，请在 config.toml 的 [xiaohongshu] 中设置 search_endpoint。"
        )
    return f"工具调用失败：{tool_name}: {error}"

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from mini_agent.plugins.context import PluginContext
from mini_agent.tools.base import Tool


MAX_STORED_MESSAGES = 200
MAX_QUERY_MESSAGES = 100


class ReadGroupMessagesArgs(BaseModel):
    group_id: Optional[str] = None
    limit: int = Field(default=20, ge=1)


def setup(ctx: PluginContext) -> None:
    async def archive(event: Dict[str, Any]) -> None:
        group_id = str(event["group_id"])
        messages = ctx.kv_get(_group_key(group_id), [])
        messages.append(
            {
                "sender_id": str(event["sender_id"]),
                "sender_name": str(event.get("sender_name") or ""),
                "text": str(event.get("text") or ""),
                "message_id": event.get("message_id"),
                "timestamp": event.get("timestamp"),
                "mentioned_bot": bool(event.get("mentioned_bot")),
            }
        )
        ctx.kv_set(_group_key(group_id), messages[-MAX_STORED_MESSAGES:])

    async def read(args: ReadGroupMessagesArgs, context: Dict[str, Any]):
        group_id = args.group_id or _current_group_id(context)
        if not group_id:
            raise ValueError("group_id is required outside a QQ group chat")

        messages = ctx.kv_get(_group_key(str(group_id)), [])
        limit = min(args.limit, MAX_QUERY_MESSAGES)
        return {"group_id": str(group_id), "messages": messages[-limit:]}

    ctx.subscribe("group_message", archive)
    ctx.register_tool(
        Tool(
            "read_group_messages",
            "Read recent messages observed in a configured QQ group.",
            ReadGroupMessagesArgs,
            read,
            inject_context=True,
        )
    )


def _group_key(group_id: str) -> str:
    return f"group:{group_id}"


def _current_group_id(context: Dict[str, Any]) -> Optional[str]:
    chat_id = str(context.get("chat_id") or "")
    if not chat_id.startswith("gqq:"):
        return None
    return chat_id.removeprefix("gqq:")

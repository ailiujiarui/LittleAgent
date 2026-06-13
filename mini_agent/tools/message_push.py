from typing import Awaitable, Callable, Dict

from pydantic import BaseModel

from mini_agent.models import OutboundMessage
from mini_agent.tools.base import Tool


Sender = Callable[[OutboundMessage], Awaitable[None]]


class MessagePushArgs(BaseModel):
    channel: str
    chat_id: str
    text: str


class MessagePushTool:
    def __init__(self) -> None:
        self._senders: Dict[str, Sender] = {}

    def register_channel(self, channel: str, sender: Sender) -> None:
        self._senders[channel] = sender

    def as_tool(self) -> Tool:
        return Tool(
            "message_push",
            "Send a text message through a registered chat channel.",
            MessagePushArgs,
            self._send,
        )

    async def _send(self, args: MessagePushArgs):
        sender = self._senders.get(args.channel)
        if sender is None:
            raise ValueError(f"unknown message channel: {args.channel}")
        await sender(
            OutboundMessage(
                channel=args.channel,
                chat_id=args.chat_id,
                text=args.text,
            )
        )
        return {"sent": True}

import asyncio
from collections import defaultdict
from typing import Awaitable, Callable, DefaultDict, List

from mini_agent.models import InboundMessage, OutboundMessage


OutboundHandler = Callable[[OutboundMessage], Awaitable[None]]


class MessageBus:
    def __init__(self) -> None:
        self._inbound_queue: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self._outbound_handlers: DefaultDict[str, List[OutboundHandler]] = defaultdict(list)

    async def publish_inbound(self, message: InboundMessage) -> None:
        await self._inbound_queue.put(message)

    async def consume_inbound(self) -> InboundMessage:
        return await self._inbound_queue.get()

    def subscribe_outbound(self, channel: str, handler: OutboundHandler) -> None:
        self._outbound_handlers[channel].append(handler)

    async def dispatch_outbound(self, message: OutboundMessage) -> None:
        for handler in list(self._outbound_handlers.get(message.channel, [])):
            await handler(message)

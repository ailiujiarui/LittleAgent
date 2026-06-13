import asyncio
import contextlib
from typing import Any, Dict, Optional, Tuple

from mini_agent.bus import MessageBus
from mini_agent.db.stores import SessionStore
from mini_agent.models import InboundMessage, OutboundMessage
from mini_agent.passive_turn import PassiveTurnPipeline


class SessionWorker:
    def __init__(
        self,
        session_key: str,
        pipeline: Any,
        bus: Optional[MessageBus] = None,
    ) -> None:
        self.session_key = session_key
        self.pipeline = pipeline
        self.bus = bus
        self._queue: asyncio.Queue[Tuple[InboundMessage, asyncio.Future]] = asyncio.Queue()
        self._task = asyncio.create_task(self._run())

    async def submit(self, message: InboundMessage) -> None:
        future = asyncio.get_running_loop().create_future()
        await self._queue.put((message, future))
        await future

    async def close(self) -> None:
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _run(self) -> None:
        while True:
            message, future = await self._queue.get()
            try:
                result = await self.pipeline.run(message)
                await self._dispatch_result(message, result)
            except Exception as exc:  # noqa: BLE001 - user-visible fallback is intentional.
                await self._dispatch_error(message, exc)
            finally:
                if not future.done():
                    future.set_result(None)
                self._queue.task_done()

    async def _dispatch_result(self, message: InboundMessage, result: Any) -> None:
        if self.bus is None or result is None:
            return
        if isinstance(result, OutboundMessage):
            await self.bus.dispatch_outbound(result)
            return
        if isinstance(result, str):
            await self.bus.dispatch_outbound(
                OutboundMessage(
                    channel=message.channel,
                    chat_id=message.chat_id,
                    text=result,
                    reply_to=message.message_id,
                )
            )

    async def _dispatch_error(self, message: InboundMessage, exc: Exception) -> None:
        if self.bus is None:
            return
        await self.bus.dispatch_outbound(
            OutboundMessage(
                channel=message.channel,
                chat_id=message.chat_id,
                text=f"Error while handling message: {exc}",
                reply_to=message.message_id,
            )
        )


class AgentLoop:
    def __init__(
        self,
        pipeline: Optional[Any] = None,
        bus: Optional[MessageBus] = None,
        session_store: Optional[SessionStore] = None,
    ) -> None:
        self.pipeline = pipeline or PassiveTurnPipeline()
        self.bus = bus
        self.session_store = session_store
        self._workers: Dict[str, SessionWorker] = {}

    async def handle_message(self, message: InboundMessage) -> None:
        if self.session_store is not None:
            self.session_store.ensure_session(message)
        worker = self._workers.get(message.session_key)
        if worker is None:
            worker = SessionWorker(message.session_key, self.pipeline, self.bus)
            self._workers[message.session_key] = worker
        await worker.submit(message)

    async def shutdown(self) -> None:
        workers = list(self._workers.values())
        self._workers.clear()
        await asyncio.gather(*(worker.close() for worker in workers), return_exceptions=True)

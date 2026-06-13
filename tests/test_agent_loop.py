import asyncio
import sqlite3

from mini_agent.models import InboundMessage


def _message(chat_id, text):
    return InboundMessage(
        channel="qq",
        chat_id=chat_id,
        sender_id="user",
        text=text,
    )


def test_same_session_messages_are_processed_fifo():
    from mini_agent.agent_loop import AgentLoop

    async def scenario():
        order = []

        class Pipeline:
            async def run(self, message):
                order.append(f"start:{message.text}")
                await asyncio.sleep(0.01)
                order.append(f"end:{message.text}")

        loop = AgentLoop(pipeline=Pipeline())
        await asyncio.gather(
            loop.handle_message(_message("123", "one")),
            loop.handle_message(_message("123", "two")),
        )
        await loop.shutdown()

        assert order == ["start:one", "end:one", "start:two", "end:two"]

    asyncio.run(scenario())


def test_different_sessions_can_process_concurrently():
    from mini_agent.agent_loop import AgentLoop

    async def scenario():
        active = 0
        both_active = asyncio.Event()

        class Pipeline:
            async def run(self, message):
                nonlocal active
                active += 1
                if active == 2:
                    both_active.set()
                await asyncio.sleep(0.05)
                active -= 1

        loop = AgentLoop(pipeline=Pipeline())
        first = asyncio.create_task(loop.handle_message(_message("123", "one")))
        second = asyncio.create_task(loop.handle_message(_message("456", "two")))

        await asyncio.wait_for(both_active.wait(), timeout=1)
        await asyncio.gather(first, second)
        await loop.shutdown()

    asyncio.run(scenario())


def test_turn_exception_dispatches_user_visible_error():
    from mini_agent.agent_loop import AgentLoop
    from mini_agent.bus import MessageBus

    async def scenario():
        bus = MessageBus()
        received = []

        class Pipeline:
            async def run(self, message):
                raise RuntimeError("boom")

        async def collect(message):
            received.append(message)

        bus.subscribe_outbound("qq", collect)
        loop = AgentLoop(pipeline=Pipeline(), bus=bus)

        await loop.handle_message(_message("123", "will fail"))
        await loop.shutdown()

        assert len(received) == 1
        assert received[0].chat_id == "123"
        assert "error" in received[0].text.lower()

    asyncio.run(scenario())


def test_session_store_creates_and_updates_sessions(tmp_path):
    from mini_agent.db.stores import SessionStore

    db_path = tmp_path / "agent.db"
    store = SessionStore(db_path)
    message = _message("gqq:678", "hello")

    session_id = store.ensure_session(message)
    store.ensure_session(message)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "select id, channel, chat_id from sessions order by id"
        ).fetchall()

    assert session_id == "qq:gqq:678"
    assert rows == [("qq:gqq:678", "qq", "gqq:678")]

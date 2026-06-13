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


def test_passive_turn_text_response_returns_assistant_output():
    from mini_agent.llm import LLMResponse
    from mini_agent.passive_turn import PassiveTurnPipeline
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        class FakeLLM:
            async def chat(self, messages, tools):
                return LLMResponse(content="assistant reply")

        pipeline = PassiveTurnPipeline(llm=FakeLLM(), tools=ToolRegistry())

        assert await pipeline.run(_message("123", "hello")) == "assistant reply"

    asyncio.run(scenario())


def test_passive_turn_tool_call_executes_and_feeds_result_back():
    from pydantic import BaseModel

    from mini_agent.llm import LLMResponse, ToolCall
    from mini_agent.passive_turn import PassiveTurnPipeline
    from mini_agent.tools.base import Tool
    from mini_agent.tools.registry import ToolRegistry

    class EchoArgs(BaseModel):
        text: str

    async def scenario():
        registry = ToolRegistry()
        registry.register(Tool("echo", "Echo text", EchoArgs, lambda args: {"echo": args.text}))

        class FakeLLM:
            def __init__(self):
                self.calls = []

            async def chat(self, messages, tools):
                self.calls.append(messages)
                if len(self.calls) == 1:
                    return LLMResponse(
                        tool_calls=[
                            ToolCall(id="call-1", name="echo", arguments={"text": "abc"})
                        ]
                    )
                return LLMResponse(content="done")

        llm = FakeLLM()
        pipeline = PassiveTurnPipeline(llm=llm, tools=registry)

        assert await pipeline.run(_message("123", "use echo")) == "done"
        assert llm.calls[1][-1]["role"] == "tool"
        assert llm.calls[1][-1]["tool_call_id"] == "call-1"
        assert '"echo":"abc"' in llm.calls[1][-1]["content"].replace(" ", "")

    asyncio.run(scenario())


def test_passive_turn_max_tool_iterations_returns_failure_message():
    from mini_agent.llm import LLMResponse, ToolCall
    from mini_agent.passive_turn import PassiveTurnPipeline
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        class FakeLLM:
            async def chat(self, messages, tools):
                return LLMResponse(
                    tool_calls=[ToolCall(id="call-1", name="missing", arguments={})]
                )

        pipeline = PassiveTurnPipeline(
            llm=FakeLLM(),
            tools=ToolRegistry(),
            max_tool_iterations=2,
        )

        result = await pipeline.run(_message("123", "loop forever"))

        assert "tool iteration limit" in result.lower()

    asyncio.run(scenario())


def test_passive_turn_persists_user_and_assistant_messages(tmp_path):
    from mini_agent.db.stores import MessageStore
    from mini_agent.llm import LLMResponse
    from mini_agent.passive_turn import PassiveTurnPipeline
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        class FakeLLM:
            async def chat(self, messages, tools):
                return LLMResponse(content="stored reply")

        store = MessageStore(tmp_path / "agent.db")
        pipeline = PassiveTurnPipeline(
            llm=FakeLLM(),
            tools=ToolRegistry(),
            message_store=store,
        )

        await pipeline.run(_message("123", "stored user"))

        assert store.list_messages("qq:123") == [
            ("user", "stored user"),
            ("assistant", "stored reply"),
        ]

    asyncio.run(scenario())

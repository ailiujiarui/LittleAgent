import asyncio

from pydantic import BaseModel


def test_tool_schema_generation_and_context_injection():
    from mini_agent.tools.base import Tool
    from mini_agent.tools.registry import ToolRegistry

    class AddArgs(BaseModel):
        a: int
        b: int

    async def add(args, context):
        return {"sum": args.a + args.b, "session": context["session_key"]}

    async def scenario():
        registry = ToolRegistry()
        registry.register(Tool("add", "Add two numbers", AddArgs, add, inject_context=True))

        schemas = registry.list_schemas()
        result = await registry.execute(
            "add",
            {"a": "2", "b": 3},
            context={"session_key": "qq:123"},
        )

        assert schemas[0]["function"]["name"] == "add"
        assert schemas[0]["function"]["parameters"]["properties"]["a"]["type"] == "integer"
        assert result.success is True
        assert result.content == {"sum": 5, "session": "qq:123"}

    asyncio.run(scenario())


def test_tool_parameter_validation_returns_error_result():
    from mini_agent.tools.base import Tool
    from mini_agent.tools.registry import ToolRegistry

    class AddArgs(BaseModel):
        a: int

    async def add(args):
        return {"value": args.a}

    async def scenario():
        registry = ToolRegistry()
        registry.register(Tool("add", "Add", AddArgs, add))

        result = await registry.execute("add", {"a": "not-an-int"})

        assert result.success is False
        assert "validation" in result.error.lower()

    asyncio.run(scenario())


def test_unknown_tool_and_tool_exception_return_error_results():
    from mini_agent.tools.base import Tool
    from mini_agent.tools.registry import ToolRegistry

    class NoArgs(BaseModel):
        pass

    async def fail(args):
        raise RuntimeError("boom")

    async def scenario():
        registry = ToolRegistry()
        registry.register(Tool("fail", "Fail", NoArgs, fail))

        missing = await registry.execute("missing", {})
        failed = await registry.execute("fail", {})

        assert missing.success is False
        assert "unknown tool" in missing.error.lower()
        assert failed.success is False
        assert "boom" in failed.error

    asyncio.run(scenario())


def test_message_push_calls_registered_sender():
    from mini_agent.tools.message_push import MessagePushTool
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        sent = []

        async def qq_sender(message):
            sent.append(message)

        push = MessagePushTool()
        push.register_channel("qq", qq_sender)

        registry = ToolRegistry()
        registry.register(push.as_tool())

        result = await registry.execute(
            "message_push",
            {"channel": "qq", "chat_id": "gqq:123", "text": "hello"},
        )

        assert result.success is True
        assert result.content == {"sent": True}
        assert sent[0].channel == "qq"
        assert sent[0].chat_id == "gqq:123"
        assert sent[0].text == "hello"

    asyncio.run(scenario())


def test_builtin_get_time_tool_is_registered():
    from mini_agent.tools.builtin import register_builtin_tools
    from mini_agent.tools.registry import ToolRegistry

    registry = ToolRegistry()
    register_builtin_tools(registry)

    assert "get_time" in registry.names()

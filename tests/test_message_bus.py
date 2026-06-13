import asyncio


def test_inbound_message_session_key_uses_channel_and_chat_id():
    from mini_agent.models import InboundMessage

    private = InboundMessage(
        channel="qq",
        chat_id="12345",
        sender_id="12345",
        text="hello",
    )
    group = InboundMessage(
        channel="qq",
        chat_id="gqq:67890",
        sender_id="12345",
        text="hello group",
    )

    assert private.session_key == "qq:12345"
    assert group.session_key == "qq:gqq:67890"


def test_outbound_message_keeps_channel_route_and_text():
    from mini_agent.models import OutboundMessage

    message = OutboundMessage(channel="qq", chat_id="gqq:1", text="pong")

    assert message.channel == "qq"
    assert message.chat_id == "gqq:1"
    assert message.text == "pong"
    assert message.metadata == {}


def test_message_bus_publish_and_consume_inbound():
    from mini_agent.bus import MessageBus
    from mini_agent.models import InboundMessage

    async def scenario():
        bus = MessageBus()
        message = InboundMessage(
            channel="qq",
            chat_id="123",
            sender_id="123",
            text="ping",
        )

        await bus.publish_inbound(message)

        assert await bus.consume_inbound() == message

    asyncio.run(scenario())


def test_message_bus_dispatches_outbound_to_channel_subscribers():
    from mini_agent.bus import MessageBus
    from mini_agent.models import OutboundMessage

    async def scenario():
        bus = MessageBus()
        received = []

        async def qq_sender(message):
            received.append(message)

        bus.subscribe_outbound("qq", qq_sender)
        await bus.dispatch_outbound(
            OutboundMessage(channel="qq", chat_id="123", text="pong")
        )

        assert [message.text for message in received] == ["pong"]

    asyncio.run(scenario())

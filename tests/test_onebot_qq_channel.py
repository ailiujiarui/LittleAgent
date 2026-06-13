import asyncio
import json

from mini_agent.models import OutboundMessage


def test_private_message_event_becomes_inbound_message():
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    channel = OneBotQQChannel(bot_id="10000")
    message = channel.parse_event(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 12345,
            "message_id": 99,
            "message": "hello",
        }
    )

    assert message is not None
    assert message.channel == "qq"
    assert message.chat_id == "12345"
    assert message.sender_id == "12345"
    assert message.text == "hello"
    assert message.message_id == "99"


def test_group_message_with_bot_at_becomes_group_inbound_message():
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    channel = OneBotQQChannel(
        bot_id="10000",
        groups={"67890": {"allow_from": set(), "require_at": True}},
    )
    message = channel.parse_event(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 67890,
            "user_id": 12345,
            "message_id": 100,
            "message": [
                {"type": "at", "data": {"qq": "10000"}},
                {"type": "text", "data": {"text": " hello group"}},
            ],
        }
    )

    assert message is not None
    assert message.chat_id == "gqq:67890"
    assert message.sender_id == "12345"
    assert message.text == "hello group"


def test_group_message_without_bot_at_is_ignored_when_require_at():
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    channel = OneBotQQChannel(
        bot_id="10000",
        groups={"67890": {"allow_from": set(), "require_at": True}},
    )

    assert (
        channel.parse_event(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 67890,
                "user_id": 12345,
                "message": "hello group",
            }
        )
        is None
    )


def test_group_message_without_bot_at_emits_plugin_event_but_not_inbound():
    from mini_agent.bus import MessageBus
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    async def scenario():
        bus = MessageBus()
        events = []

        async def emit(event_name, event):
            events.append((event_name, event))

        channel = OneBotQQChannel(
            bot_id="10000",
            bus=bus,
            groups={"67890": {"allow_from": set(), "require_at": True}},
            event_emitter=emit,
        )

        result = await channel.handle_event(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 67890,
                "user_id": 12345,
                "message_id": 101,
                "time": 1710000000,
                "sender": {"nickname": "Alice"},
                "message": "ordinary chatter",
            }
        )

        assert result is None
        assert bus._queue().empty()
        assert events == [
            (
                "group_message",
                {
                    "group_id": "67890",
                    "sender_id": "12345",
                    "sender_name": "Alice",
                    "text": "ordinary chatter",
                    "message_id": "101",
                    "timestamp": 1710000000,
                    "mentioned_bot": False,
                },
            )
        ]

    asyncio.run(scenario())


def test_group_message_with_bot_at_emits_plugin_event_and_inbound():
    from mini_agent.bus import MessageBus
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    async def scenario():
        bus = MessageBus()
        events = []

        async def emit(event_name, event):
            events.append((event_name, event))

        channel = OneBotQQChannel(
            bot_id="10000",
            bus=bus,
            groups={"67890": {"allow_from": set(), "require_at": True}},
            event_emitter=emit,
        )

        result = await channel.handle_event(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 67890,
                "user_id": 12345,
                "message": [
                    {"type": "at", "data": {"qq": "10000"}},
                    {"type": "text", "data": {"text": " summarize"}},
                ],
            }
        )

        assert result is not None
        assert (await bus.consume_inbound()).text == "summarize"
        assert events[0][0] == "group_message"
        assert events[0][1]["mentioned_bot"] is True
        assert events[0][1]["text"] == "summarize"

    asyncio.run(scenario())


def test_group_message_from_unconfigured_group_is_ignored():
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    channel = OneBotQQChannel(
        bot_id="10000",
        groups={"67890": {"allow_from": set(), "require_at": False}},
    )

    assert (
        channel.parse_event(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 11111,
                "user_id": 12345,
                "message": "hello",
            }
        )
        is None
    )


def test_group_message_from_unauthorized_sender_is_ignored():
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    channel = OneBotQQChannel(
        bot_id="10000",
        groups={"67890": {"allow_from": {"12345"}, "require_at": False}},
    )

    assert (
        channel.parse_event(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 67890,
                "user_id": 99999,
                "message": "hello",
            }
        )
        is None
    )


def test_unauthorized_private_sender_is_ignored():
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    channel = OneBotQQChannel(bot_id="10000", allowed_private_users={"12345"})

    assert (
        channel.parse_event(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 99999,
                "message": "hello",
            }
        )
        is None
    )


def test_outbound_private_message_builds_onebot_send_private_payload():
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    channel = OneBotQQChannel(bot_id="10000")

    assert channel.build_send_payload(
        OutboundMessage(channel="qq", chat_id="12345", text="pong")
    ) == {
        "action": "send_private_msg",
        "params": {"user_id": 12345, "message": "pong"},
    }


def test_outbound_group_message_builds_onebot_send_group_payload():
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    channel = OneBotQQChannel(bot_id="10000")

    assert channel.build_send_payload(
        OutboundMessage(channel="qq", chat_id="gqq:67890", text="pong")
    ) == {
        "action": "send_group_msg",
        "params": {"group_id": 67890, "message": "pong"},
    }


def test_onebot_channel_handle_event_publishes_to_bus():
    from mini_agent.bus import MessageBus
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    async def scenario():
        bus = MessageBus()
        channel = OneBotQQChannel(bot_id="10000", bus=bus)

        await channel.handle_event(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "message": "hello",
            }
        )

        assert (await bus.consume_inbound()).text == "hello"

    asyncio.run(scenario())


def test_onebot_channel_logs_published_private_event():
    from mini_agent.bus import MessageBus
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    async def scenario():
        logs = []
        bus = MessageBus()
        channel = OneBotQQChannel(bot_id="10000", bus=bus, logger=logs.append)

        await channel.handle_event(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "message": "hello",
            }
        )

        assert "OneBot inbound private 12345: hello" in logs

    asyncio.run(scenario())


def test_onebot_channel_send_writes_payload_to_socket():
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    async def scenario():
        sent = []

        class Socket:
            async def send(self, data):
                sent.append(json.loads(data))

        channel = OneBotQQChannel(bot_id="10000")
        await channel.send_via_socket(
            Socket(),
            OutboundMessage(channel="qq", chat_id="12345", text="pong"),
        )

        assert sent == [
            {
                "action": "send_private_msg",
                "params": {"user_id": 12345, "message": "pong"},
            }
        ]

    asyncio.run(scenario())


def test_onebot_channel_logs_socket_connect_and_disconnect():
    from mini_agent.channels.onebot_qq import OneBotQQChannel

    async def scenario():
        logs = []

        class Socket:
            remote_address = ("127.0.0.1", 10000)

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        channel = OneBotQQChannel(bot_id="10000", logger=logs.append)

        await channel._handle_socket(Socket())

        assert logs == [
            "OneBot socket connected: ('127.0.0.1', 10000)",
            "OneBot socket disconnected: ('127.0.0.1', 10000)",
        ]

    asyncio.run(scenario())

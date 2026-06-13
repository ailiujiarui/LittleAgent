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

import asyncio


def test_http_json_source_normalization_and_judge_json_parsing():
    from mini_agent.proactive.loop import parse_judge_json
    from mini_agent.proactive.sources import normalize_json_items

    items = normalize_json_items(
        "news",
        [{"id": "1", "title": "Agent update", "url": "https://example.test/a", "summary": "body"}],
    )
    judge = parse_judge_json('{"score": 0.8, "message": "worth sending"}')

    assert items[0].source == "news"
    assert items[0].key == "1"
    assert items[0].title == "Agent update"
    assert items[0].content == "body"
    assert judge.score == 0.8
    assert judge.message == "worth sending"


def test_proactive_tick_pushes_threshold_item_and_dedupes(tmp_path):
    from mini_agent.proactive.loop import JudgeResult, ProactiveLoop, ProactiveStore
    from mini_agent.proactive.sources import SourceItem
    from mini_agent.tools.message_push import MessagePushTool
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        sent = []

        async def sender(message):
            sent.append(message)

        push = MessagePushTool()
        push.register_channel("qq", sender)
        registry = ToolRegistry()
        registry.register(push.as_tool())

        class Source:
            async def fetch(self):
                return [
                    SourceItem(
                        source="news",
                        key="1",
                        title="Agent update",
                        url="https://example.test/a",
                        content="body",
                    )
                ]

        class Judge:
            async def judge(self, item):
                return JudgeResult(score=0.9, message=f"Push: {item.title}")

        loop = ProactiveLoop(
            sources=[Source()],
            judge=Judge(),
            store=ProactiveStore(tmp_path / "agent.db"),
            tools=registry,
            target_channel="qq",
            target_chat_id="123",
            threshold=0.65,
        )

        assert await loop.tick() == 1
        assert await loop.tick() == 0
        assert sent[0].text == "Push: Agent update"

    asyncio.run(scenario())


def test_proactive_skips_when_busy_or_limited(tmp_path):
    from mini_agent.proactive.loop import JudgeResult, ProactiveLoop, ProactiveStore
    from mini_agent.proactive.sources import SourceItem
    from mini_agent.tools.message_push import MessagePushTool
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        sent = []

        async def sender(message):
            sent.append(message)

        push = MessagePushTool()
        push.register_channel("qq", sender)
        registry = ToolRegistry()
        registry.register(push.as_tool())

        class Source:
            def __init__(self):
                self.counter = 0

            async def fetch(self):
                self.counter += 1
                return [
                    SourceItem(
                        source="news",
                        key=str(self.counter),
                        title=f"Item {self.counter}",
                        url="",
                        content="",
                    )
                ]

        class Judge:
            async def judge(self, item):
                return JudgeResult(score=1.0, message=item.title)

        busy_loop = ProactiveLoop(
            sources=[Source()],
            judge=Judge(),
            store=ProactiveStore(tmp_path / "busy.db"),
            tools=registry,
            target_channel="qq",
            target_chat_id="123",
            is_session_busy=lambda session_key: True,
        )
        limited_loop = ProactiveLoop(
            sources=[Source()],
            judge=Judge(),
            store=ProactiveStore(tmp_path / "limited.db"),
            tools=registry,
            target_channel="qq",
            target_chat_id="123",
            cooldown_minutes=60,
            daily_max_pushes=1,
        )

        assert await busy_loop.tick() == 0
        assert await limited_loop.tick() == 1
        assert await limited_loop.tick() == 0
        assert len(sent) == 1

    asyncio.run(scenario())

import asyncio

import pytest


def test_scan_skills_and_selects_least_recently_run(tmp_path):
    from mini_agent.drift.loop import DriftStore, scan_skills, select_least_recently_run

    skills_dir = tmp_path / "drift" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "a.md").write_text("skill a", encoding="utf-8")
    (skills_dir / "b.md").write_text("skill b", encoding="utf-8")

    store = DriftStore(tmp_path)
    store.record_run("a", status="finished", summary="done")

    skills = scan_skills(tmp_path)
    selected = select_least_recently_run(skills, store)

    assert [skill.name for skill in skills] == ["a", "b"]
    assert selected.name == "b"


def test_finish_drift_validation_requires_matching_message_result():
    from mini_agent.drift.loop import FinishDriftArgs, validate_finish_drift

    validate_finish_drift(
        FinishDriftArgs(one_line="done", next="none", message_result="sent"),
        message_sent=True,
    )

    with pytest.raises(ValueError):
        validate_finish_drift(
            FinishDriftArgs(one_line="done", next="none", message_result="silent"),
            message_sent=True,
        )


def test_drift_allows_only_one_message_push(tmp_path):
    from mini_agent.drift.loop import DriftLoop, DriftStore
    from mini_agent.llm import LLMResponse, ToolCall
    from mini_agent.tools.message_push import MessagePushTool
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        (tmp_path / "drift" / "skills").mkdir(parents=True)
        (tmp_path / "drift" / "skills" / "review.md").write_text("review", encoding="utf-8")
        sent = []

        async def sender(message):
            sent.append(message)

        push = MessagePushTool()
        push.register_channel("qq", sender)
        registry = ToolRegistry()
        registry.register(push.as_tool())

        class FakeLLM:
            def __init__(self):
                self.calls = 0

            async def chat(self, messages, tools):
                self.calls += 1
                if self.calls <= 2:
                    return LLMResponse(
                        tool_calls=[
                            ToolCall(
                                id=f"push-{self.calls}",
                                name="message_push",
                                arguments={"channel": "qq", "chat_id": "123", "text": "hello"},
                            )
                        ]
                    )
                return LLMResponse(
                    tool_calls=[
                        ToolCall(
                            id="finish",
                            name="finish_drift",
                            arguments={
                                "one_line": "done",
                                "next": "none",
                                "message_result": "sent",
                            },
                        )
                    ]
                )

        loop = DriftLoop(
            workspace=tmp_path,
            llm=FakeLLM(),
            tools=registry,
            store=DriftStore(tmp_path),
            max_steps=3,
            min_interval_minutes=0,
        )

        result = await loop.run_once(proactive_pushed=False)

        assert result.status == "finished"
        assert len(sent) == 1

    asyncio.run(scenario())


def test_drift_max_steps_records_unfinished(tmp_path):
    from mini_agent.drift.loop import DriftLoop, DriftStore
    from mini_agent.llm import LLMResponse, ToolCall
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        (tmp_path / "drift" / "skills").mkdir(parents=True)
        (tmp_path / "drift" / "skills" / "review.md").write_text("review", encoding="utf-8")

        class FakeLLM:
            async def chat(self, messages, tools):
                return LLMResponse(
                    tool_calls=[ToolCall(id="x", name="missing", arguments={})]
                )

        store = DriftStore(tmp_path)
        loop = DriftLoop(
            workspace=tmp_path,
            llm=FakeLLM(),
            tools=ToolRegistry(),
            store=store,
            max_steps=1,
            min_interval_minutes=0,
        )

        result = await loop.run_once(proactive_pushed=False)

        assert result.status == "unfinished"
        assert store.latest_run()["status"] == "unfinished"

    asyncio.run(scenario())

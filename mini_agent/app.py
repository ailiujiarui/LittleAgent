import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from mini_agent.agent_loop import AgentLoop
from mini_agent.bootstrap import init_workspace
from mini_agent.bus import MessageBus
from mini_agent.channels.onebot_qq import OneBotQQChannel
from mini_agent.config import AppConfig, ProactiveSourceConfig
from mini_agent.db.migrations import apply_migrations
from mini_agent.db.stores import MessageStore, SessionStore
from mini_agent.dashboard.server import create_dashboard_app
from mini_agent.drift.loop import DriftLoop, DriftStore
from mini_agent.llm import OpenAICompatibleLLM
from mini_agent.mcp.registry import McpRegistry
from mini_agent.memory.store import MemoryStore
from mini_agent.passive_turn import PassiveTurnPipeline
from mini_agent.plugins.group_messages import setup as setup_group_messages
from mini_agent.plugins.manager import PluginManager
from mini_agent.plugins.xiaohongshu_search import create_setup as setup_xiaohongshu_search
from mini_agent.proactive.loop import JudgeResult, ProactiveLoop, ProactiveStore
from mini_agent.proactive.sources import HTTPJSONSource, RSSSource
from mini_agent.tools.builtin import register_builtin_tools, register_memory_tools
from mini_agent.tools.message_push import MessagePushTool
from mini_agent.tools.registry import ToolRegistry


class AppRuntime:
    def __init__(
        self,
        config: AppConfig,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.config = config
        self.logger = logger or _print_line
        self.workspace = Path(config.workspace)
        self.db_path = self.workspace / "agent.db"
        self.bus: Optional[MessageBus] = None
        self.tools: Optional[ToolRegistry] = None
        self.onebot: Optional[OneBotQQChannel] = None
        self.agent_loop: Optional[AgentLoop] = None
        self.mcp: Optional[McpRegistry] = None
        self.plugins: Optional[PluginManager] = None
        self.proactive_loop: Optional[ProactiveLoop] = None
        self.drift_loop: Optional[DriftLoop] = None
        self.background_tasks = []
        self.dashboard_server: Optional[Any] = None
        self.dashboard_task: Optional[asyncio.Task] = None
        self._runtime_summary: Dict[str, Any] = {}

    def build_services(self) -> Dict[str, Any]:
        init_workspace(self.workspace)
        apply_migrations(self.db_path)

        self.bus = MessageBus()
        self.tools = ToolRegistry()
        register_builtin_tools(self.tools)

        memory = MemoryStore(self.workspace)
        register_memory_tools(self.tools, memory)

        push_tool = MessagePushTool()
        self.tools.register(push_tool.as_tool())

        self.plugins = PluginManager(
            workspace=self.workspace,
            tools=self.tools,
            builtin_plugins={
                "group_messages": setup_group_messages,
                "xiaohongshu_search": setup_xiaohongshu_search(
                    endpoint=self.config.xiaohongshu.search_endpoint or None,
                    api_key=self.config.xiaohongshu.search_api_key or None,
                ),
            },
        )
        plugin_result = self.plugins.load_all()

        self.onebot = OneBotQQChannel(
            bot_id=self.config.onebot.bot_uin,
            bus=self.bus,
            allowed_private_users=self.config.onebot.allow_private,
            groups=self.config.onebot.groups,
            logger=self.logger,
            event_emitter=self.plugins.emit,
            path=self.config.onebot.path,
            access_token=self.config.onebot.access_token,
        )
        self.bus.subscribe_outbound("qq", self.onebot.send)
        push_tool.register_channel("qq", self.onebot.send)

        llm = OpenAICompatibleLLM(
            base_url=self.config.llm.base_url,
            api_key=self.config.llm.api_key,
            model=self.config.llm.model,
        )
        pipeline = PassiveTurnPipeline(
            llm=llm,
            tools=self.tools,
            message_store=MessageStore(self.db_path),
            memory_store=memory,
        )
        self.agent_loop = AgentLoop(
            pipeline=pipeline,
            bus=self.bus,
            session_store=SessionStore(self.db_path),
        )

        self.mcp = McpRegistry(
            config_path=self.workspace / "mcp_servers.json",
            tools=self.tools,
        )
        proactive_sources = _build_proactive_sources(self.config.proactive.sources)
        if self.config.proactive.enabled:
            self.proactive_loop = ProactiveLoop(
                sources=proactive_sources,
                judge=_LLMProactiveJudge(llm),
                store=ProactiveStore(self.db_path),
                tools=self.tools,
                target_channel=self.config.proactive.target_channel,
                target_chat_id=self.config.proactive.target_chat_id,
                threshold=self.config.proactive.threshold,
                cooldown_minutes=self.config.proactive.cooldown_minutes,
                daily_max_pushes=self.config.proactive.daily_max_pushes,
            )
        else:
            self.proactive_loop = None

        if self.config.drift.enabled:
            self.drift_loop = DriftLoop(
                workspace=self.workspace,
                llm=llm,
                tools=self.tools,
                store=DriftStore(self.workspace),
                max_steps=self.config.drift.max_steps,
                min_interval_minutes=self.config.drift.min_interval_minutes,
            )
        else:
            self.drift_loop = None

        return {
            "workspace": str(self.workspace),
            "tools": self.tools.get_registered_names(),
            "plugins": plugin_result.model_dump(),
            "mcp": {
                "enabled": self.config.mcp.enabled,
                "configured_servers": len(self.mcp._load_config()),
            },
            "proactive": {
                "enabled": self.config.proactive.enabled,
                "sources": [source.name for source in proactive_sources],
            },
            "drift": {
                "enabled": self.config.drift.enabled,
                "max_steps": self.config.drift.max_steps,
            },
            "dashboard": {
                "enabled": self.config.dashboard.enabled,
                "host": self.config.dashboard.host,
                "port": self.config.dashboard.port,
            },
        }

    def dry_run(self) -> Dict[str, Any]:
        return self.build_services()

    def startup_lines(self):
        return [
            f"workspace: {self.workspace}",
            (
                "OneBot listening: "
                f"ws://{self.config.onebot.host}:"
                f"{self.config.onebot.port}{self.config.onebot.path}"
            ),
            f"bot_uin: {self.config.onebot.bot_uin}",
        ]

    async def start_runtime_services(self, start_onebot: bool = True) -> Dict[str, Any]:
        assert self.onebot is not None
        assert self.mcp is not None

        summary: Dict[str, Any] = {}
        if self.config.mcp.enabled:
            await self.mcp.connect_all()
            summary["mcp"] = {
                "connected": self.mcp.server_tools,
                "failed": self.mcp.failed,
            }
        else:
            summary["mcp"] = {"connected": {}, "failed": {}}

        if start_onebot:
            await self.onebot.start(
                host=self.config.onebot.host,
                port=self.config.onebot.port,
            )
        self._runtime_summary = summary
        if self.config.dashboard.enabled:
            summary["dashboard"] = await self._start_dashboard()
        else:
            summary["dashboard"] = {"running": False}
        if self.proactive_loop is not None or self.drift_loop is not None:
            self.background_tasks.append(asyncio.create_task(self._run_background_loop()))
        self._runtime_summary = summary
        return summary

    async def stop_runtime_services(self) -> None:
        if self.dashboard_server is not None:
            self.dashboard_server.should_exit = True
        if self.dashboard_task is not None:
            try:
                await asyncio.wait_for(self.dashboard_task, timeout=5)
            except asyncio.TimeoutError:
                self.dashboard_task.cancel()
                await asyncio.gather(self.dashboard_task, return_exceptions=True)
            self.dashboard_task = None
            self.dashboard_server = None

        for task in self.background_tasks:
            task.cancel()
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        self.background_tasks.clear()
        if self.onebot is not None:
            await self.onebot.stop()
        if self.agent_loop is not None:
            await self.agent_loop.shutdown()
        if self.mcp is not None:
            await self.mcp.close_all()

    async def run_forever(self) -> None:
        self.build_services()
        assert self.bus is not None
        assert self.onebot is not None
        assert self.agent_loop is not None

        await self.start_runtime_services(start_onebot=True)
        for line in self.startup_lines():
            self.logger(line)
        self.logger("Waiting for NapCat reverse WebSocket and QQ messages. Press Ctrl+C to stop.")
        consumer = asyncio.create_task(self._consume_inbound())
        try:
            await asyncio.Event().wait()
        finally:
            consumer.cancel()
            await self.stop_runtime_services()

    async def _consume_inbound(self) -> None:
        assert self.bus is not None
        assert self.agent_loop is not None
        while True:
            message = await self.bus.consume_inbound()
            await self.agent_loop.handle_message(message)

    async def _run_background_loop(self) -> None:
        while True:
            proactive_pushed = 0
            if self.proactive_loop is not None:
                proactive_pushed = await self.proactive_loop.tick()
            if self.drift_loop is not None:
                await self.drift_loop.run_once(proactive_pushed=bool(proactive_pushed))
            await asyncio.sleep(self.config.proactive.interval_seconds)

    async def _start_dashboard(self) -> Dict[str, Any]:
        import uvicorn

        dashboard_app = create_dashboard_app(
            self.workspace,
            status={
                "running": True,
                "mcp": self._runtime_summary.get("mcp", {}),
            },
        )
        config = uvicorn.Config(
            dashboard_app,
            host=self.config.dashboard.host,
            port=self.config.dashboard.port,
            log_level="warning",
        )
        self.dashboard_server = uvicorn.Server(config)
        self.dashboard_task = asyncio.create_task(self.dashboard_server.serve())

        for _ in range(100):
            if self.dashboard_server.started:
                break
            if self.dashboard_task.done():
                await self.dashboard_task
            await asyncio.sleep(0.01)

        return {
            "running": True,
            "url": f"http://{self.config.dashboard.host}:{self.config.dashboard.port}",
        }


def _print_line(message: str) -> None:
    print(message, flush=True)


def _build_proactive_sources(configs: list[ProactiveSourceConfig]):
    sources = []
    for config in configs:
        source_type = config.type.lower().replace("-", "_")
        if source_type == "rss":
            sources.append(RSSSource(config.name, config.url))
        elif source_type in {"http_json", "json"}:
            sources.append(HTTPJSONSource(config.name, config.url))
        else:
            raise ValueError(f"unsupported proactive source type: {config.type}")
    return sources


class _LLMProactiveJudge:
    def __init__(self, llm: OpenAICompatibleLLM) -> None:
        self.llm = llm

    async def judge(self, item) -> JudgeResult:
        from mini_agent.proactive.loop import parse_judge_json

        response = await self.llm.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Return strict JSON: "
                        '{"score": 0.0, "message": "message to push"}'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"source={item.source}\n"
                        f"title={item.title}\n"
                        f"url={item.url}\n"
                        f"content={item.content}"
                    ),
                },
            ],
            [],
        )
        return parse_judge_json(response.content)

import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from mini_agent.agent_loop import AgentLoop
from mini_agent.bootstrap import init_workspace
from mini_agent.bus import MessageBus
from mini_agent.channels.onebot_qq import OneBotQQChannel
from mini_agent.config import AppConfig
from mini_agent.db.migrations import apply_migrations
from mini_agent.db.stores import MessageStore, SessionStore
from mini_agent.llm import OpenAICompatibleLLM
from mini_agent.mcp.registry import McpRegistry
from mini_agent.memory.store import MemoryStore
from mini_agent.passive_turn import PassiveTurnPipeline
from mini_agent.plugins.group_messages import setup as setup_group_messages
from mini_agent.plugins.manager import PluginManager
from mini_agent.plugins.xiaohongshu_search import create_setup as setup_xiaohongshu_search
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

        return {
            "workspace": str(self.workspace),
            "tools": self.tools.get_registered_names(),
            "plugins": plugin_result.model_dump(),
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

    async def run_forever(self) -> None:
        self.build_services()
        assert self.bus is not None
        assert self.onebot is not None
        assert self.agent_loop is not None

        await self.onebot.start(
            host=self.config.onebot.host,
            port=self.config.onebot.port,
        )
        for line in self.startup_lines():
            self.logger(line)
        self.logger("Waiting for NapCat reverse WebSocket and QQ messages. Press Ctrl+C to stop.")
        consumer = asyncio.create_task(self._consume_inbound())
        try:
            await asyncio.Event().wait()
        finally:
            consumer.cancel()
            await self.onebot.stop()
            await self.agent_loop.shutdown()
            if self.mcp is not None:
                await self.mcp.close_all()

    async def _consume_inbound(self) -> None:
        assert self.bus is not None
        assert self.agent_loop is not None
        while True:
            message = await self.bus.consume_inbound()
            await self.agent_loop.handle_message(message)


def _print_line(message: str) -> None:
    print(message, flush=True)

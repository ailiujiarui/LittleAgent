from datetime import datetime, timezone

from pydantic import BaseModel

from mini_agent.tools.base import Tool
from mini_agent.tools.registry import ToolRegistry


class GetTimeArgs(BaseModel):
    pass


async def _get_time(args: GetTimeArgs):
    return {"iso": datetime.now(timezone.utc).isoformat()}


def register_builtin_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "get_time",
            "Return the current UTC time in ISO-8601 format.",
            GetTimeArgs,
            _get_time,
        )
    )

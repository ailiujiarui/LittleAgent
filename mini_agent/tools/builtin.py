from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, Field

from mini_agent.memory.store import MemoryStore
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


class ReadMemoryArgs(BaseModel):
    target: str


class WriteMemoryArgs(BaseModel):
    target: str
    content: str
    keywords: List[str] = Field(default_factory=list)


class SearchMemoryArgs(BaseModel):
    query: str


class MergePendingMemoryArgs(BaseModel):
    merged_content: str


def register_memory_tools(registry: ToolRegistry, store: MemoryStore) -> None:
    async def read_memory(args: ReadMemoryArgs):
        return {"content": store.read_file(args.target)}

    async def write_memory(args: WriteMemoryArgs):
        if args.target == "PENDING.md":
            store.append_pending(args.content, args.keywords)
        else:
            store.write_file(args.target, args.content)
        return {"written": True}

    async def search_memory(args: SearchMemoryArgs):
        return {"items": [item.content for item in store.search(args.query)]}

    async def merge_pending_memory(args: MergePendingMemoryArgs):
        backup = store.merge_pending(args.merged_content)
        return {"merged": True, "backup": str(backup)}

    registry.register(
        Tool(
            "read_memory",
            "Read a Markdown memory file.",
            ReadMemoryArgs,
            read_memory,
        )
    )
    registry.register(
        Tool(
            "write_memory",
            "Write memory content. PENDING.md appends, other targets replace.",
            WriteMemoryArgs,
            write_memory,
        )
    )
    registry.register(
        Tool(
            "search_memory",
            "Search memory snippets by keyword.",
            SearchMemoryArgs,
            search_memory,
        )
    )
    registry.register(
        Tool(
            "merge_pending_memory",
            "Replace MEMORY.md with merged content and clear PENDING.md.",
            MergePendingMemoryArgs,
            merge_pending_memory,
        )
    )

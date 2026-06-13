import asyncio


def test_memory_store_initializes_markdown_files(tmp_path):
    from mini_agent.memory.store import MemoryStore

    store = MemoryStore(tmp_path)

    assert (store.memory_dir / "SELF.md").exists()
    assert (store.memory_dir / "MEMORY.md").exists()
    assert (store.memory_dir / "RECENT_CONTEXT.md").exists()
    assert (store.memory_dir / "HISTORY.md").exists()
    assert (store.memory_dir / "PENDING.md").exists()


def test_prompt_blocks_include_core_memory_files(tmp_path):
    from mini_agent.memory.store import MemoryStore

    store = MemoryStore(tmp_path)
    (store.memory_dir / "SELF.md").write_text("identity", encoding="utf-8")
    (store.memory_dir / "MEMORY.md").write_text("likes tea", encoding="utf-8")
    (store.memory_dir / "RECENT_CONTEXT.md").write_text("talked about agents", encoding="utf-8")

    blocks = store.build_prompt_blocks(session_key="qq:123", query="tea agents")

    assert [block.name for block in blocks] == [
        "SELF.md",
        "MEMORY.md",
        "RECENT_CONTEXT.md",
    ]
    assert [block.content for block in blocks] == [
        "identity",
        "likes tea",
        "talked about agents",
    ]


def test_append_pending_and_keyword_search(tmp_path):
    from mini_agent.memory.store import MemoryStore

    store = MemoryStore(tmp_path)

    store.append_pending("User likes jasmine tea", keywords=["jasmine", "tea"])
    results = store.search("what tea?")

    assert "User likes jasmine tea" in (store.memory_dir / "PENDING.md").read_text(
        encoding="utf-8"
    )
    assert [item.content for item in results] == ["User likes jasmine tea"]


def test_merge_pending_writes_backup_and_clears_pending(tmp_path):
    from mini_agent.memory.store import MemoryStore

    store = MemoryStore(tmp_path)
    (store.memory_dir / "MEMORY.md").write_text("old memory", encoding="utf-8")
    store.append_pending("new fact", keywords=["fact"])

    backup = store.merge_pending("old memory\nnew fact\n")

    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "old memory"
    assert (store.memory_dir / "MEMORY.md").read_text(encoding="utf-8") == (
        "old memory\nnew fact\n"
    )
    assert (store.memory_dir / "PENDING.md").read_text(encoding="utf-8") == ""


def test_memory_tools_read_write_search_and_merge(tmp_path):
    from mini_agent.memory.store import MemoryStore
    from mini_agent.tools.builtin import register_memory_tools
    from mini_agent.tools.registry import ToolRegistry

    async def scenario():
        store = MemoryStore(tmp_path)
        registry = ToolRegistry()
        register_memory_tools(registry, store)

        written = await registry.execute(
            "write_memory",
            {
                "target": "PENDING.md",
                "content": "User studies agents",
                "keywords": ["agents"],
            },
        )
        searched = await registry.execute("search_memory", {"query": "agents"})
        read = await registry.execute("read_memory", {"target": "PENDING.md"})
        merged = await registry.execute(
            "merge_pending_memory",
            {"merged_content": "User studies agents\n"},
        )

        assert written.success is True
        assert searched.content["items"] == ["User studies agents"]
        assert read.content["content"].strip() == "User studies agents"
        assert merged.success is True

    asyncio.run(scenario())

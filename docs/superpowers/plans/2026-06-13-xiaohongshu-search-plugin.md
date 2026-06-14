# Xiaohongshu Search Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a built-in tool plugin that searches Xiaohongshu through `xiaohongshu-mcp` by default, keeps JSON endpoint compatibility, filters posts by requirements, sorts newest first, and returns reply-ready links.

**Architecture:** Implement `mini_agent/plugins/xiaohongshu_search.py` as a focused plugin with normalization helpers and one registered tool. The default path uses HTTP MCP Streamable HTTP with initialize/session handling against `xiaohongshu-mcp`; a compatible JSON endpoint remains supported. Wire it into `AppRuntime` as a built-in plugin and document configuration in the Chinese README without storing API keys or cookies.

**Tech Stack:** Python 3.9+, httpx, Pydantic 2, pytest

---

### Task 1: Plugin Tool Behavior

**Files:**
- Create: `mini_agent/plugins/xiaohongshu_search.py`
- Test: `tests/test_plugins.py`

- [x] Write a failing test that loads the plugin, calls a fake fetcher, filters
  keyword matches, skips URL-less items, sorts newest first, and returns link
  text.
- [x] Write a failing test for missing `XHS_SEARCH_ENDPOINT`.
- [x] Implement the minimal plugin with injectable fetcher support for tests.
- [x] Add HTTP MCP tests for latest sorting, Streamable HTTP initialize/session handling, feed-card normalization, and actionable connection/timeout errors.
- [x] Run `py -m pytest tests/test_plugins.py -q`.

### Task 2: Runtime Wiring

**Files:**
- Modify: `mini_agent/app.py`
- Test: `tests/test_app_cli.py`

- [x] Write a failing test that `AppRuntime.dry_run()` registers
  `search_xiaohongshu_posts`.
- [x] Add the plugin to the built-in plugin map.
- [x] Run `py -m pytest tests/test_app_cli.py -q`.

### Task 3: Documentation

**Files:**
- Modify: `README.zh-CN.md`

- [x] Document `XHS_SEARCH_ENDPOINT`, optional `XHS_SEARCH_API_KEY`, expected
  JSON shape, and tool behavior.
- [x] Avoid real API keys, cookies, account IDs, or local adapter URLs.
- [x] Run Markdown link/sensitive scans.

### Task 4: Full Verification And Push

**Files:**
- No extra production changes expected.

- [x] Run `py -m pytest`.
- [x] Run `git diff --check`.
- [x] Run staged sensitive scan.
- [ ] Commit with a Chinese message.
- [ ] Push to `origin/master` and verify remote hash.

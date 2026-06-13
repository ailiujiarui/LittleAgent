# Xiaohongshu Search Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a built-in tool plugin that searches a configured Xiaohongshu JSON endpoint, filters posts by requirements, sorts newest first, and returns reply-ready links.

**Architecture:** Implement `mini_agent/plugins/xiaohongshu_search.py` as a focused plugin with normalization helpers and one registered tool. Wire it into `AppRuntime` as a built-in plugin and document configuration in the Chinese README without storing API keys.

**Tech Stack:** Python 3.9+, httpx, Pydantic 2, pytest

---

### Task 1: Plugin Tool Behavior

**Files:**
- Create: `mini_agent/plugins/xiaohongshu_search.py`
- Test: `tests/test_plugins.py`

- [ ] Write a failing test that loads the plugin, calls a fake fetcher, filters
  keyword matches, skips URL-less items, sorts newest first, and returns link
  text.
- [ ] Write a failing test for missing `XHS_SEARCH_ENDPOINT`.
- [ ] Implement the minimal plugin with injectable fetcher support for tests.
- [ ] Run `py -m pytest tests/test_plugins.py -q`.

### Task 2: Runtime Wiring

**Files:**
- Modify: `mini_agent/app.py`
- Test: `tests/test_app_cli.py`

- [ ] Write a failing test that `AppRuntime.dry_run()` registers
  `search_xiaohongshu_posts`.
- [ ] Add the plugin to the built-in plugin map.
- [ ] Run `py -m pytest tests/test_app_cli.py -q`.

### Task 3: Documentation

**Files:**
- Modify: `README.zh-CN.md`

- [ ] Document `XHS_SEARCH_ENDPOINT`, optional `XHS_SEARCH_API_KEY`, expected
  JSON shape, and tool behavior.
- [ ] Avoid real API keys, cookies, account IDs, or local adapter URLs.
- [ ] Run Markdown link/sensitive scans.

### Task 4: Full Verification And Push

**Files:**
- No extra production changes expected.

- [ ] Run `py -m pytest`.
- [ ] Run `git diff --check`.
- [ ] Run staged sensitive scan.
- [ ] Commit with a Chinese message.
- [ ] Push to `origin/master` and verify remote hash.

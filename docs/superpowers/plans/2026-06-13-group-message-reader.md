# Group Message Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Archive online messages from configured QQ groups and expose recent messages through a plugin tool without triggering replies to ordinary chatter.

**Architecture:** `OneBotQQChannel` emits a normalized plugin event before applying the existing `require_at` reply gate. A built-in plugin stores a rolling per-group archive in `PluginKVStore` and registers an injected-context tool for reading it. `AppRuntime` loads the built-in plugin and wires the plugin event emitter into the channel.

**Tech Stack:** Python 3.9+, asyncio, Pydantic 2, SQLite, pytest

---

### Task 1: Group Event Hook

**Files:**
- Modify: `mini_agent/channels/onebot_qq.py`
- Test: `tests/test_onebot_qq_channel.py`

- [x] Write a failing test showing a configured non-mention group message emits
  `group_message` but does not enter the inbound bus.
- [x] Write a failing test showing a mention emits the plugin event and still
  enters the inbound bus.
- [x] Add an optional event emitter and split group observation from the
  existing reply gate.
- [x] Run `py -m pytest tests/test_onebot_qq_channel.py -q`.

### Task 2: Group Message Plugin

**Files:**
- Create: `mini_agent/plugins/group_messages.py`
- Modify: `mini_agent/plugins/manager.py`
- Test: `tests/test_plugins.py`

- [x] Write failing tests for archive/read, current-group inference, and rolling
  retention.
- [x] Allow `PluginManager` callers to provide built-in plugin setup functions.
- [x] Implement `group_messages.setup(ctx)` with a `group_message` subscription
  and `read_group_messages` tool.
- [x] Run `py -m pytest tests/test_plugins.py -q`.

### Task 3: Runtime Wiring

**Files:**
- Modify: `mini_agent/app.py`
- Test: `tests/test_app_cli.py`

- [x] Write a failing runtime test proving the plugin is loaded and a
  non-mention group message is readable without entering the inbound bus.
- [x] Load the built-in plugin in `AppRuntime` and pass `plugins.emit` to the
  OneBot channel.
- [x] Run `py -m pytest tests/test_app_cli.py -q`.

### Task 4: Full Verification

**Files:**
- No production changes expected.

- [x] Run `py -m pytest`.
- [x] Inspect `git diff --check`.
- [x] Confirm agent and NapCat remain stopped after verification.

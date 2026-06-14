# Chinese README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Chinese README that accurately explains the project's advantages and link it from the existing English README.

**Architecture:** Keep `README.md` as the short English entry and add `README.zh-CN.md` as the full Chinese document. The Chinese document describes only implemented capabilities, uses placeholder configuration values, and avoids local secrets or runtime data.

**Tech Stack:** Markdown, Python/Pytest project documentation

---

### Task 1: Chinese README

**Files:**
- Create: `README.zh-CN.md`

- [x] Draft the document with sections for positioning, advantages, capability
  overview, architecture, quick start, QQ/NapCat setup, group message reader,
  plugin development, safety, testing, and current boundaries.
- [x] Use only placeholder secrets such as `${DEEPSEEK_API_KEY}` and sample IDs
  such as `123456789` or `222222222`.
- [x] Avoid claiming capabilities not wired into `AppRuntime`.

### Task 2: English README Link

**Files:**
- Modify: `README.md`

- [x] Add a short language navigation line near the title:
  `[中文说明](README.zh-CN.md)`.
- [x] Leave the existing English quick start intact.

### Task 3: Verification

**Files:**
- No production code changes expected.

- [x] Run a Markdown link/path check for `README.zh-CN.md` and `README.md`.
- [x] Run a staged/document sensitive-info scan for API keys, local QQ IDs,
  WebUI tokens, NapCat login data paths, and local config file content.
- [x] Run `git diff --check`.
- [x] Optionally run `py -m pytest` only if non-doc files changed.

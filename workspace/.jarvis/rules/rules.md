# JARVIS Rules

*Glob-scoped behavioral rules. Each rule specifies which files/paths it applies to.*

---

## Content Parsing — Preserve User Intent

**Scope**: `src/agent.py`, all command parsing
**Rule**: When extracting topics, filenames, or commands from user input, NEVER strip away the actual meaningful content — only remove known filler words.
**Example (fixed behavior)**:
- Input: `create "test.md" the content fill with who is tony stark in 1 sentence`
- ❌ WRONG: extract `who is` as the topic (filler stripping removed the real query)
- ✅ CORRECT: pass the full `user_input` to the LLM so nothing is lost

**Why**: Early implementations stripped "who is tony stark in 1 sentence" down to nothing, producing empty files. Always prefer passing full context to the LLM over fragmentary regex extraction.

---

## Memory Index Sync

**Scope**: `src/memory.py`
**Rule**: The memory index (`memory/index.md`) must be updated after ANY memory write (conversation, fact, or decision).

---

## Auto-Logging

**Scope**: `src/agent.py`
**Rule**: Every significant operation (file create/edit/delete, terminal command, internet browse, memory learn) appends to `log.md` with timestamp.

---

## Safety Boundaries

**Scope**: All modules
**Rule**: File operations and terminal execution must stay within `workspace/`. Path traversal is rejected.

---

## Approval Requirements

**Scope**: `terminal_exec`, `web_access`
**Rule**: Terminal commands and internet browsing require user approval (configurable via `settings.md`).

---

## Score: All rules are globally scoped unless specified otherwise.

# Commands

*Slash commands — quick shortcuts for common tasks. Loaded at startup.*

---

## /help
**Description**: List all available commands and capabilities.
**Action**: Show capabilities (same as "what can you do").

## /status
**Description**: Show current status — branch, model, memory, skills loaded.
**Action**: Display JARVIS status.

## /summarize
**Description**: Summarize a file or directory.
**Usage**: `/summarize [filename|folder]`
**Action**: Route to summarizer skill.

## /remember
**Description**: Save a fact to memory.
**Usage**: `/remember [key] is [value]`
**Action**: Route to memory_ops skill.

## /search
**Description**: Search the web.
**Usage**: `/search [query]`
**Action**: Route to web_access skill.

## /list
**Description**: List files in workspace.
**Action**: Route to file_crud skill.

## /clear
**Description**: Clear the screen.
**Action**: Execute `cls`.

---

*Commands can be extended by editing this file. Restart JARVIS to reload.*
# JARVIS Skills Registry

*Each skill describes a capability JARVIS can invoke. Skills are loaded from this file at startup.*

---

## File Operations

**Name**: `file_crud`
**Trigger**: "create X", "read X", "edit X", "delete X", "list files"
**Description**: Create, read, edit, delete, and list files in the workspace.
- `create file.md about [topic]` — create a markdown file with LLM-generated content
- `read file.md` — display file contents
- `edit "file.md" change "old" to "new"` — replace text in a file
- `delete file.md` — remove a file
- `list files` — show workspace contents

**Implementation**: `src/file_manager.py` → `FileManager` class

---

## Terminal Execution

**Name**: `terminal_exec`
**Trigger**: "run X", "execute X", or any direct shell command (git, python, pip, mkdir, etc.)
**Description**: Execute terminal commands with cwd locked to the workspace.
- Requires approval before execution (configurable in settings.md)
- Commands are logged to `workspace/terminal_log.json`
- Supports: git, python, pip, mkdir, rmdir, ipconfig, cls, tasklist, etc.

**Implementation**: `src/terminal_executor.py` → `TerminalExecutor` class

---

## Internet Access

**Name**: `web_access`
**Trigger**: "browse [url]", "search for [query]", "look up X", "google X"
**Description**: Fetch web pages and search the web.
- Requires approval before browsing (configurable in settings.md)
- Can save research to `workspace/research/`
- Uses DuckDuckGo HTML scraping for search (no API key required)

**Implementation**: `src/internet.py` → `Internet` class

---

## Memory & Learning

**Name**: `memory_ops`
**Trigger**: "remember that X is Y", "I am X", "I work as X"
**Description**: Store facts, preferences, and conversation summaries.
- `remember that [key] is [value]` — save a fact to memory
- `I work as a developer` — learns user role
- Automatically updates `memory/index.md` and `memory/facts_user.md`
- Loads relevant memory into system prompt on startup

**Implementation**: `src/memory.py` → `Memory` class

---

## Summarization

**Name**: `summarize_docs`
**Trigger**: "summarize [file]", "summarize all files in [folder]", "list summaries"
**Description**: Read files and produce concise summaries in various styles.
- `summarize file.md` — concise summary
- `summarize file.md as bullets` — bullet-point style
- `summarize file.md as mindmap` — mind-map style
- `summarize all files in folder` — combined summary
- `list summaries` — show all generated summaries
- Saves to `summaries/summary_*.md`

**Implementation**: `src/summarizer.py` → `Summarizer` class

---

## Autonomous Planning

**Name**: `auto_plan`
**Trigger**: "organize my notes", "write a script that X", "learn about X and create Y", "setup project"
**Description**: Break high-level goals into concrete multi-step actions and execute them.
- Creates a plan using the LLM
- Executes read/write/run/search/remember steps
- Recovers from partial failures via alternative strategies
- Logs decisions to `memory/decisions.md`

**Implementation**: `src/memory.py` → `AutonomousPlanner` class
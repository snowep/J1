# JARVIS Memory

*Persistent memory files. JARVIS reads these to recall facts, conversations, and decisions.*

---

## Contents

- **User Preferences** — `facts_user.md` (key facts about the user)
- **Daily Conversations** — `conversation_YYYY-MM-DD.md`
- **Decisions** — `decisions.md` (autonomous actions taken)
- **Index** — `index.md` (auto-generated link map)

## How It Works

1. JARVIS stores facts as key-value pairs in `facts_*.md`
2. Conversations are appended to daily logs
3. The index is regenerated after every memory change
4. Memory context is injected into the LLM system prompt on startup

## Editing

All memory files are plain markdown — you can read and edit them directly in Obsidian or any text editor. JARVIS will pick up changes on the next startup.

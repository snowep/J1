# JARVIS Brain Directory — Overview

This `.jarvis/` folder is JARVIS's "brain" — a self-describing directory that defines what JARVIS can do, how it behaves, and what it remembers. Everything here is human-readable markdown (plus JSON settings), fully editable [1].

---

## Structure

```
workspace/
├── .jarvis/
│   ├── settings.md       # Core config: model, permissions, workspace paths
│   ├── index.md          # Auto-generated capability index
│   ├── memory/           # Persistent memory (facts, conversations, decisions)
│   │   ├── README.md
│   │   └── ...
│   ├── skills/           # Capabilities JARVIS can invoke
│   │   └── skills.md     # file_crud, terminal_exec, web_access, etc.
│   ├── rules/            # Glob-scoped behavioral rules
│   │   └── rules.md      # content parsing, safety, approvals, logging
│   ├── commands/         # (empty — slash commands)
│   ├── hooks/            # (empty — event-triggered scripts)
│   └── output-styles/    # (empty — response format presets)
```

## How JARVIS Uses This

On startup and before each message, JARVIS scans `.jarvis/`, loads all `.md` content into context (or a summarized version), and uses it to:

- **Know what it can do** — from `skills/`
- **Behave correctly** — from `rules/`
- **Recall facts** — from `memory/`
- **Apply permissions** — from `settings.md`

## Editing

Just edit any markdown file here. Changes are picked up on next startup. No code changes needed.

## Design Principles

1. **Transparent** — everything is human-readable
2. **Editable** — change behavior without touching code
3. **Self-loading** — JARVIS reads this automatically
4. **Extensible** — add skills, rules, agents by adding files

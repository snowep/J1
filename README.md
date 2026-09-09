# JARVIS OS

Personal AI assistant framework with autonomous reasoning, persistent memory, and real system access — built to be genuinely helpful, not just a chat wrapper.

**v0.9.0** · Python 3.12+ · Runs on Windows / macOS / Linux

---

## What's different

Most AI assistants live in a chat box. JARVIS OS has a workspace it can see, files it can edit, a terminal it can use, and skills it can learn — all gated by a permissions system that stays out of your way when things are routine and asks before doing something destructive.

The Phase 9 `core/` refactor makes every component modular, testable, and secure:

```
core/
├── utils.py          path safety (commonpath), filler stripping, JSON repair
├── llm.py            multi-provider LLM (OpenAI / Ollama / mock fallback)
├── supervisor.py     permission modes (auto / ask / deny), dry-run, audit trail
├── executor.py       workspace-bound terminal, shell-free builtins
├── filesystem.py     CRUD operations, path traversal blocked via commonpath
├── internet.py       http/https-only web access (file:// and ftp:// blocked)
├── memory.py         conversation history + YAML-fact storage + decision log
├── skill_manager.py  YAML-frontmatter skills, sandboxed execution
├── action_parser.py  extracts/repairs/validates ```action``` blocks from LLM
├── action_executor.py supervisor-gated action routing to all handlers
└── agent.py          thin orchestrator tying everything together
```

**74 pytest tests passing** · `tests/` directory with full coverage

---

## Quick start

```bash
# Clone the repo
git clone <repo-url> && cd OS

# Install dependencies
pip install requests beautifulsoup4 pyyaml

# Run tests (74 tests, no LLM required)
python -m pytest tests/ -v

# Run the agent in interactive mode (works offline with mock LLM)
python main.py

# Single command
python main.py --once "list files"
python main.py --once "run python --version"
python main.py --once "remember that my name is Tony"
```

---

## Architecture

### Request flow

```
User input
  → Memory (add to history + context)
  → LLM (OpenAI / Ollama / mock)
  → Action Parser (extract ```action``` blocks, JSON repair)
  → Supervisor (permission check: auto / ask / deny / dry-run)
  → Action Executor (dispatch to handler: filesystem, terminal, internet, skills, memory)
  → LLM followup (summarize what was done)
  → Memory (add response)
  → User
```

### Offline / mock mode

When no LLM backend is configured, JARVIS falls back to:
1. **Auto-detect**: OpenAI if API key present → Ollama if localhost reachable → mock
2. **Keyword handler**: `list files`, `read <file>`, `run <cmd>`, `list skills`, `remember that <k> is <v>`
3. **Mock responses**: deterministic, no network required — great for testing and demos

---

## Security model

| Layer | Mechanism |
|---|---|
| **Path safety** | `os.path.commonpath` + `realpath` — replaces insecure `startswith()` checks |
| **Command injection** | `sanitize_command()` rejects `;`, `|`, `\|`, backticks, `$()` |
| **Shell disabled** | `subprocess.run(argv, shell=False)` — no shell interpretation; Windows builtins handled in-process |
| **CWD enforcement** | `commonpath` on `realpath` values — `../` escapes blocked |
| **Permissions** | Per-category modes: `auto` / `ask` / `deny` + auto-allow list + always-deny list |
| **Dry-run** | `dry_run: true` in config — supervisor logs all intended actions without executing |
| **Internet** | Only `http`/`https` schemes accepted — `file://`, `ftp://`, `javascript:` blocked |
| **Skills** | Subprocess isolation or restricted builtins — no raw `exec()` with full access |

---

## Configuration

`config.yaml` (or `.jarvis/config.json`):

```yaml
llm:
  provider: auto        # auto | openai | ollama | mock
  model: auto
  api_key: ""           # or set JARVIS_API_KEY env var
  api_base: ""          # custom OpenAI-compatible endpoint
  temperature: 0.2
  retries: 3
  backoff: 2.0

permissions:
  terminal: ask         # auto | ask | deny
  file_write: auto
  file_read: auto
  file_delete: ask
  internet: ask
  skill: ask

dry_run: false          # log all actions without executing
```

---

## Skills

Skills are markdown files in `.jarvis/skills/` with YAML frontmatter:

```markdown
---
name: double
description: Double a number
params:
  - name: x
    type: int
    required: true
    description: Number to double
---

Doubles the given number.

```python
def run(x, **kwargs):
    return f"double({x}) = {x * 2}"
```
```

Skills run in a sandboxed subprocess by default — no access to JARVIS internals.

---

## Memory

- **Conversation history**: rolling window, oldest half auto-summarized to markdown
- **YAML facts**: `memory/facts.md` — structured key/value storage (user preferences, project context)
- **Decision log**: `memory/decisions.md` — append-only record of what JARVIS did and why

---

## Project structure

```
OS/
├── core/                 Phase 9 modular core (see above)
├── src/                  Legacy monolithic modules (being migrated)
├── workspace/            User workspace — JARVIS's working directory
│   ├── .jarvis/          Config, skills, memory
│   ├── research/         Auto-saved web research excerpts
│   └── *.md              User files
├── tests/                pytest test suite (74 tests)
├── config.yaml           Default configuration
├── main.py               CLI entry point
├── run.py                Legacy entry point
├── demo_autonomous_recovery.py   E2E autonomous task demo
└── README.md             This file
```

---

## Testing

```bash
# Full test suite
python -m pytest tests/ -v

# By module
python -m pytest tests/test_utils.py -v
python -m pytest tests/test_executor.py -v
python -m pytest tests/test_action_parser.py -v
python -m pytest tests/test_supervisor.py -v
python -m pytest tests/test_filesystem.py -v
python -m pytest tests/test_skill_manager.py -v
python -m pytest tests/test_memory.py -v

# Smoke tests (no pytest required)
python _smoke_core.py
python _smoke_parser.py
python _smoke_agent.py
python _smoke_skills_mem_exec.py
```

---

## License

Internal project — not for distribution.

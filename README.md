# JARVIS OS

**JARVIS OS** is a personal AI operating layer — a local assistant that can use your filesystem, terminal, web, memory, and skills through a strictly enforced policy boundary.

## Current Status

**Phase 10 — jarvis/ Refactor (In Progress)**

The system now runs a complete, policy-gated stack:

- **Domain Models** (`jarvis/agent/state.py`): Typed action, observation, plan, and result objects
- **Tool Registry** (`jarvis/tools/registry.py`): 29 tool definitions, all validated before execution
- **Policy Engine** (`jarvis/policy/engine.py`): Risk classification, approval gates, deny/allow modes
- **Tools** (`jarvis/tools/`): Filesystem, terminal (no shell=True), internet (SSRF blocked), memory, self-model, audit
- **Executor** (`jarvis/tools/executor.py`): Per-action execution with error handling and dry-run support
- **Agent Loop** (`jarvis/agent/loop.py`): Read → build context → plan → authorize → execute → observe → verify → recover
- **Memory** (`jarvis/memory/store.py`): Markdown-first persistent memory with provenance
- **Skills** (`jarvis/skills/`): Manifest-based skill loading with trust levels
- **Self-Model** (`jarvis/self/model.py`): Current state tracking, capabilities, goals, failures
- **Audit** (`jarvis/audit/`): Structured event logging

### Verified Capabilities

| Feature | Status | Tests |
|---|---|---|
| Filesystem operations | ✅ Working | 9 |
| Terminal execution | ✅ Working | 9 |
| Policy enforcement | ✅ Working | 4 |
| Memory persistence | ✅ Working | 2 |
| Audit logging | ✅ Working | 1 |
| Self-model | ✅ Working | 1 |
| Agent loop (O/V/R) | ✅ Working | 3 |
| NL → action mapping | ✅ Working | 2 |
| Test runner | ✅ Working | 1 |
| Integration | ✅ Working | 10 |
| **Total** | **15** | **51** |

## Quick Start

```bash
# Set workspace directory
mkdir workspace

# Run tests
python -m pytest tests/

# Run the integration test
python tests/test_integration.py

# Run the full regression
python _final_check.py
```

## Directory Structure

```
OS/
├── jarvis/              # Core package (new, authoritative)
│   ├── agent/           # Agent loop, state, planner
│   ├── audit/           # Audit logging
│   ├── config/          # Configuration loader
│   ├── dashboard/       # Dashboard module
│   ├── llm/             # LLM client & providers
│   ├── memory/          # Markdown-first memory store
│   ├── policy/          # Policy engine
│   ├── sandbox/         # Sandbox manager
│   ├── self/            # Self-model
│   ├── skills/          # Skill system
│   └── tools/           # All tools
│       ├── filesystem.py
│       ├── terminal.py
│       ├── internet.py
│       ├── memory.py
│       ├── registry.py
│       └── executor.py
├── workspace/           # User workspace (auto-created)
├── memory/               # Canonical Markdown memory
├── tests/                # Test suite
│   ├── test_integration.py  # Full stack test (15 checks)
│   └── ...
├── _check.py             # Sanity checker (legacy)
├── _check2.py            # Sanity checker (legacy)
├── _final_check.py       # Full regression test
└── README.md
```

## Security Model

- **No raw execution**: LLM never executes code directly — only the tool registry can
- **Policy gates**: Every action passes through the policy engine
- **Fail closed**: Deny-by-default for unknown tools, write operations, ASK without handler
- **Resource limits**: Timeouts, output caps, file size limits
- **SSRF protection**: Blocked private/metadata IPs at DNS and redirect levels
- **Audit trail**: Structured Markdown logging for every action

## Configuration

Edit `config.yaml`:

```yaml
permissions:
  filesystem: allow     # allow | ask | deny
  terminal: ask        # allow | ask | deny
  internet: deny       # allow | ask | deny
  memory: allow        # allow | ask | deny
  skill: ask           # allow | ask | deny
  system: ask          # allow | ask | deny

paths:
  workspace: workspace
  memory: memory
  audit: memory/audit
  skills: skills
```

## Skills

Skills are Markdown files with YAML frontmatter in `skills/`:

```markdown
---
name: fetch-url
version: 1.0.0
description: Fetch a URL and return content
required_tools: [internet.fetch]
risk_level: high
trust_level: external_unverified
---

# fetch-url

Fetch content from any URL and return as Markdown.
```

Trust levels: `built-in`, `verified`, `user_approved`, `external_unverified`, `blocked`

## Memory Model

Memory is Markdown-first and human-readable:

```markdown
---
id: ...
type: preference
confidence: 0.95
source: conversation
---

# Extracted Preference

The user prefers short answers unless detail is requested.
```

## Architecture Principles

- **Markdown-first**: All memory/knowledge stored as `.md` files
- **Policy gates**: Structured authorization before every action
- **Bounded autonomy**: LLM does not control execution
- **Observe before acting**: Read state before modifying
- **Recover gracefully**: Errors trigger assessment, not retry loops
- **Resource limits**: Every tool opt-in, resource-capped
- **Auditability**: Structured logging across all layers

## Current Limitations

- No dashboard / visualization UI (pending)
- No planning engine beyond natural-language mapping
- No web search thresholds
- No true level-5 OS isolation but sandbox interface is reproducible
- Memory retrieval is keyword-based (no semantic search)
- No drive-first PDF/parsing skills

## Goals

- [ ] Bounded autonomy with graduated approval
- [ ] Self-update pipeline (patch, test, deploy, rollback)
- [ ] Skill learning from observation
- [ ] Memory decay and summarization
- [ ] Regression testing in CI
- [ ] Distribution as Docker image
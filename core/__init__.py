"""
JARVIS OS — Core package.

Phase-9 refactor: modular, secure, testable core components that replace the
monolithic src/agent.py orchestrator.

Modules:
    utils           — shared helpers (path safety, filler stripping, text utils)
    llm             — LLM client with retry + fallback
    supervisor      — permission checks (auto/ask/deny, dry-run)
    executor        — safe terminal execution
    filesystem      — workspace-safe file CRUD
    internet        — http/https-restricted web access
    memory          — persistent history + fact storage
    skill_manager   — YAML-frontmatter skills, sandboxed execution
    action_parser   — extract/repair/validate ```action``` blocks
    action_executor — supervisor-gated action routing
    agent           — thin orchestrator tying it all together
"""

__version__ = "0.9.0"
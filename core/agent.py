"""
JARVIS OS — core/agent.py

Thin agent orchestrator (Phase 9).

Flow for each user message:
    1. Build context: recent history + facts + available skills + system prompt.
    2. Call the LLM (core/llm) — it may return prose OR ```action``` blocks.
    3. Parse output with core/action_parser.
    4. If actions -> execute each with core/action_executor (supervisor-gated),
       feed results back to the LLM for a final user-facing reply.
    5. If no actions -> pass the LLM's prose straight through.
    6. Log the interaction to memory.

Offline/keyword fallback: when no LLM is available (mock provider), the agent
still handles direct "list files", "read X", "run X", "create skill X"
commands through built-in keyword handling — the agent stays useful without
any backend.
"""

import logging
from typing import Any, Dict, List, Optional

from .action_parser import ActionParser, action_to_text
from .action_executor import ActionExecutor
from .executor import Executor
from .filesystem import FileSystem
from .internet import Internet
from .llm import LLMClient
from .memory import Memory
from .skill_manager import SkillManager
from .supervisor import Supervisor

log = logging.getLogger("jarvis.agent")

SYSTEM_PROMPT = """You are JARVIS, a capable, concise AI assistant for the JARVIS OS workspace.

## Personality
- Be direct, brief, and genuinely helpful. No fluff.
- You can act autonomously *within the workspace* — take initiative, don't just
  answer questions.  When a task has clear next steps, DO them.
- If a request is ambiguous, ask ONE clarifying question rather than guessing
  wrong.  Prefer action over hand-wringing.
- Security matters: you NEVER escape the workspace, NEVER touch dangerous
  commands, and NEVER access the internet without explicit permission.

## Available tools (emit as ```action``` blocks)
```action
{"type": "terminal", "command": "ls -la"}
```
```action
{"type": "file_write", "path": "notes.md", "content": "..."}
```
```action
{"type": "file_read", "path": "notes.md"}
```
```action
{"type": "file_edit", "path": "notes.md", "old": "...", "new": "..."}
```
```action
{"type": "file_append", "path": "notes.md", "content": "..."}
```
```action
{"type": "file_delete", "path": "notes.md"}
```
```action
{"type": "file_list", "path": "."}
```
```action
{"type": "internet_search", "query": "..."}
```
```action
{"type": "internet_browse", "url": "https://..."}
```
```action
{"type": "skill", "skill": "hello_world", "params": {"message": "hi"}}
```
```action
{"type": "skill_list"}
```
```action
{"type": "memory_remember", "key": "user_name", "value": "Tony"}
```
```action
{"type": "memory_recall", "key": "user_name"}
```
```action
{"type": "summarize", "path": "report.md"}
```

## Rules
- Emit one or more ```action``` blocks when tools are needed; otherwise answer
  in plain prose and it will be passed to the user directly.
- After executing actions you may continue with a short prose summary.
- Never emit ```action``` blocks inside a ```action``` block.  Keep JSON strict:
  double quotes, no trailing commas.  If in doubt, run multiple blocks in order.
"""


class Agent:
    """Minimal orchestrator wiring parser -> executor -> LLM."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        workspace_path: str = "workspace",
        skills_dir: str = ".jarvis/skills",
        memory_path: str = ".jarvis/memory",
    ):
        config = config or {}
        self.config = config

        # Core components (order matters: memory/skills have no deps)
        self.memory = Memory(memory_path=memory_path)
        self.skills = SkillManager(skills_dir=skills_dir)
        self.fs = FileSystem(workspace_path=workspace_path)
        self.supervisor = Supervisor(
            permissions=config.get("permissions"),
            dry_run=bool(config.get("dry_run", False)),
        )
        self.executor = Executor(
            workspace_path=workspace_path,
            supervisor=self.supervisor,
        )
        self.internet = Internet()
        self.llm = LLMClient(config.get("llm") or {})
        self.parser = ActionParser()
        self.executor_actions = ActionExecutor(
            filesystem=self.fs,
            executor=self.executor,
            internet=self.internet,
            skills=self.skills,
            memory=self.memory,
            supervisor=self.supervisor,
        )

        if self.llm.provider == "mock":
            log.info("No LLM backend available — running with mock/offline fallback")

    # ── main entry ──────────────────────────────────────────────────────────

    def process(self, user_input: str) -> str:
        """Process one user message -> assistant reply string."""
        user_input = (user_input or "").strip()
        if not user_input:
            return "Say something, boss."

        self.memory.add_message("user", user_input)

        # 1) Build context
        context = self.memory.get_context()
        facts = self.memory.get_facts()
        if facts:
            fact_text = "; ".join(f"{k}={v.get('value', '')}" for k, v in facts.items())
            context.append({"role": "system", "content": f"Known facts: {fact_text}"})
        context.append({"role": "system", "content": self.skills.describe_all()})
        context.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

        # 2) Call LLM with retry/fallback
        reply = self.llm.complete(context)

        # 3) Parse for actions
        actions = None
        try:
            actions = self.parser.parse(reply)
        except Exception:
            log.exception("Action parsing failed; treating as chat")
            actions = None

        # 4) Execute actions if any, then produce final text
        if actions:
            outputs = []
            for action in actions:
                result = self.executor_actions.execute(action)
                outputs.append(f"{action_to_text(action)} -> {result.get('output', '')}")
            execution_summary = "\n".join(outputs)
            # Ask the LLM to summarize what it did (if real backend), else return raw
            if self.llm.provider == "mock":
                final = "Actions executed:\n" + execution_summary
            else:
                followup = context + [
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": "Summarize what you did in 1-3 short lines."},
                ]
                try:
                    final = self.llm.complete(followup)
                except Exception:
                    final = "Actions executed:\n" + execution_summary
            self.memory.add_message("assistant", final)
            return final

        # 5) No actions -> keyword fallback for offline usability
        if self.llm.provider == "mock":
            final = self._keyword_fallback(user_input)
        else:
            final = reply
        self.memory.add_message("assistant", final)
        return final

    # ── offline keyword fallback ────────────────────────────────────────────

    def _keyword_fallback(self, user_input: str) -> str:
        """Handle common commands without an LLM backend."""
        low = user_input.lower()

        if "list files" in low or low.strip() in ("ls", "list", "dir"):
            r = self.fs.list(".")
            if r.get("success"):
                return "\n".join(f"- {i['path']}" for i in r["items"]) or "(empty workspace)"
            return f"⚠️ {r.get('error')}"

        if low.startswith("read ") or low.startswith("show "):
            path = user_input.split(" ", 1)[1].strip()
            r = self.fs.read(path)
            if r.get("success"):
                return r["content"]
            return f"⚠️ {r.get('error')}"

        if low.startswith("run ") or low.startswith("execute "):
            cmd = user_input.split(" ", 1)[1].strip()
            r = self.executor.execute(cmd)
            if r.get("status") == "success":
                return r.get("stdout") or "OK"
            return f"⚠️ {r.get('error') or r.get('stderr')}"

        if "create skill" in low:
            # minimal: list skills (create skill flow is LLM-driven)
            return self.skills.describe_all()

        if "list skills" in low:
            return self.skills.describe_all()

        if "remember that" in low:
            # "remember that X is Y"
            rest = user_input.split("remember that", 1)[1]
            if " is " in rest:
                k, v = rest.split(" is ", 1)
                self.memory.store_fact(k.strip(), v.strip())
                return f"✅ Remembered: {k.strip()} = {v.strip()}"
            return "Format: remember that <key> is <value>"

        return (
            f"(offline mode — no LLM backend) I can: list files, read <file>, run <cmd>, "
            f"list skills, remember that <k> is <v>. You said: {user_input[:80]}"
        )
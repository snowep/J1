"""
Agent loop — the core orchestrator.

Flow:
1. Build context (memory + self-model + recent actions + system state)
2. Send to LLM (untrusted planner)
3. Validate LLM output (action parser)
4. Authorize via policy engine
5. Execute via tool executor
6. Observe changes
7. Verify outcome
8. Recover or replan on failure
9. Repeat until done or limit hit
10. Produce final answer

The LLM never runs unobserved.
Every execution is structured and recoverable.
"""

import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..agent.state import (
    Action,
    ActionStatus,
    ActionResult,
    ApprovalRequest,
    Observation,
    Plan,
    PlanStatus,
    RiskLevel,
    SystemState,
    VerificationResult,
)
from ..audit.events import AuditLogger
from ..config.loader import Config
from ..memory.store import MemoryStore
from ..policy.engine import PolicyEngine
from ..tools.executor import ToolExecutor
from ..tools.registry import ToolRegistry, create_default_registry

log = logging.getLogger("jarvis.agent")

# System prompt for the LLM planner
SYSTEM_PROMPT = """You are JARVIS, a capable personal AI assistant.

You plan and execute structured actions to accomplish user goals.

RULES:
- You MUST return your response as a valid JSON action block:
```json
{"tool": "tool.name", "arguments": {...}}
```
- Use ONLY the tools listed below.
- If you need multiple steps, return each as a separate action block.
- Always verify your actions succeeded.
- If an action fails, try an alternative approach.
- Never execute dangerous commands without explicit user confirmation.

AVAILABLE TOOLS:
{tools}

MEMORY CONTEXT:
{memory}

SELF-MODEL:
{self_model}

CURRENT STATE:
{state}

When the user gives a goal, plan the steps needed, then execute them one at a time.
After each execution, verify the result before proceeding.
If everything is done, respond with a plain-text summary (no action block)."""

# Fallback prompts for offline/mock mode
FALLBACK_PROMPT = """You are JARVIS, a capable personal AI assistant.

You plan and execute structured actions to accomplish user goals.

RULES:
- Return your response as a valid JSON action block:
```json
{"tool": "tool.name", "arguments": {...}}
```
- Use ONLY the tools listed below.
- If you need multiple steps, return each as a separate action block.
- Always verify your actions succeeded.
- If an action fails, try an alternative approach.

AVAILABLE TOOLS:
{tools}

When the user gives a goal, plan the steps needed, then execute them one at a time.
After each execution, verify the result before proceeding.
If everything is done, respond with a plain-text summary (no action block)."""


class AgentLoop:
    """The core agent loop that orchestrates planning, execution, and recovery.

    Responsibilities:
    - Build context from memory, self-model, and system state
    - Call the LLM with the system prompt
    - Parse LLM output into structured actions
    - Authorize actions via policy engine
    - Execute via tool executor
    - Observe and verify outcomes
    - Recover or replan on failure
    - Produce final answer

    The LLM never runs unobserved.
    Every execution is structured and recoverable.
    """

    def __init__(
        self,
        config: Config,
        tool_registry: Optional[ToolRegistry] = None,
        executor: Optional[ToolExecutor] = None,
        memory: Optional[MemoryStore] = None,
        audit: Optional[AuditLogger] = None,
        llm_caller: Optional[Callable[[str, str], str]] = None,
    ):
        self.config = config
        self.tool_registry = tool_registry or create_default_registry()
        self.audit = audit or AuditLogger(
            audit_dir=config.get("paths.audit", "memory/audit")
        )
        self.memory = memory or MemoryStore(
            memory_dir=config.get("paths.memory", "memory")
        )
        self.executor = executor or ToolExecutor(
            self.tool_registry,
            PolicyEngine(
                permissions=config.permissions,
                tool_registry=self.tool_registry,
            ),
        )
        self.llm_caller = llm_caller  # injectable for testing / offline

        self.system_state = SystemState()
        self._max_iterations = config.get("security.max_plan_actions", 20)
        self._iteration_count = 0

    def run(self, user_input: str) -> str:
        """Main entry point: process user input and return a response.

        This is the core agent loop.
        """
        self._iteration_count = 0
        self.system_state.current_goal = user_input

        # 1) Build context
        context = self._build_context(user_input)

        # 2) Send to LLM
        llm_response = self._call_llm(user_input, context)

        # 3) Parse LLM output
        actions = self._parse_response(llm_response)

        # 4) If no actions, the LLM gave a direct answer
        if not actions:
            return llm_response

        # 5) Execute actions (the loop)
        return self._execute_loop(actions)

    def _build_context(self, user_input: str) -> str:
        """Build context from memory, self-model, and system state."""
        parts = []

        # Memory context
        memory_context = self.memory.get_context_for_llm()
        if memory_context:
            parts.append(f"MEMORY CONTEXT:\n{memory_context}")

        # System state
        parts.append(f"CURRENT STATE:")
        parts.append(f"- Session: {self.system_state.session_id}")
        parts.append(f"- Goal: {self.system_state.current_goal}")
        parts.append(f"- Active plan: {self.system_state.active_plan or 'none'}")
        parts.append(f"- Tool usage: {self.system_state.tool_usage}")

        return "\n\n".join(parts)

    def _call_llm(self, user_input: str, context: str) -> str:
        """Call the LLM with user input and context.

        If no LLM caller is set, returns a simple plan.
        """
        if self.llm_caller:
            try:
                return self.llm_caller(user_input, context)
            except Exception as e:
                log.error("LLM call failed: %s", e)
                # Fall through to simple plan

        # Simple plan for testing / offline mode
        return self._simple_plan(user_input)

    def _simple_plan(self, user_input: str) -> str:
        """Generate a simple plan without LLM — deterministic fallback for common operations.

        Uses natural language understanding to map user intent to structured actions.
        """
        text = user_input.lower().strip()
        text = text.replace("please ", "").replace("can you ", "").replace("could you ", "")

        # Determine what the user is asking
        if any(k in text for k in ["what is", "who is", "explain", "how to", "describe", "tell me"]):
            return f"I would help with: {user_input}"

        # Filesystem write (write/create/make file)
        if any(k in text for k in ["write", "create", "make", "save", "store", "put"]):
            # Try to extract filename
            filename = self._extract_filename(user_input)
            if filename:
                content = self._extract_content_after(user_input, filename)
                return f'```json\n{{"tool": "filesystem.write", "arguments": {{"path": "{filename}", "content": "{content}"}}}}\n```'
            else:
                # Use a default filename based on content
                return f'```json\n{{"tool": "filesystem.write", "arguments": {{"path": "output.md", "content": "{user_input}"}}}}\n```'

        # Read (read/show/display file)
        if any(k in text for k in ["read", "show", "display", "view", "open"]):
            filename = self._extract_filename(user_input)
            if filename:
                return f'```json\n{{"tool": "filesystem.read", "arguments": {{"path": "{filename}"}}}}\n```'

        # List (list/show files/folders)
        if any(k in text for k in ["list", "show", "display", "see"]) and any(k in text for k in ["file", "folder", "directory", "ls", "contents"]):
            return '```json\n{"tool": "filesystem.list", "arguments": {"path": "."}}\n```'

        # Terminal (run/execute command)
        if any(k in text for k in ["run", "execute", "command", "terminal", "shell"]):
            cmd = self._extract_command(user_input)
            return f'```json\n{{"tool": "terminal.run", "arguments": {{"command": "{cmd}"}}}}\n```'

        # Internet search
        if any(k in text for k in ["search", "find", "look up", "what is", "who is"]):
            # Check local memory first
            memory_result = self._search_local(user_input)
            if memory_result:
                return f"I found this in my memory:\n{memory_result}"
            return f'```json\n{{"tool": "internet.search", "arguments": {{"query": "{user_input}"}}}}\n```'

        # Default: just say what we'd do
        return f"I would help with: {user_input}"

    def _extract_filename(self, text: str) -> str:
        """Extract a filename from user input."""
        # Look for file extensions
        import re
        m = re.search(r'([\w\-\.]+\.(md|txt|py|json|yaml|yml|csv|log))', text)
        if m:
            return m.group(1)
        # Look for quoted strings
        m = re.search(r'["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
        # Look for common file-like words at the end
        words = text.split()
        for w in reversed(words):
            if "." in w and len(w) > 2:
                return w
        return ""

    def _extract_content_after(self, text: str, filename: str) -> str:
        """Extract content that comes after a filename in the text."""
        idx = text.lower().find(filename.lower())
        if idx == -1:
            return text
        rest = text[idx + len(filename):].strip()
        return rest if rest else text

    def _extract_command(self, text: str) -> str:
        """Extract a command from user input."""
        # Try to find the command portion
        text_lower = text.lower()
        for prefix in ["run ", "execute ", "do ", "perform "]:
            if prefix in text_lower:
                return text[text_lower.find(prefix) + len(prefix):].strip()
        # Look for os-specific commands
        import re
        m = re.search(r'\b(ls|dir|echo|pwd|cat|type|cd|mkdir|rmdir|docker|git|python|pip)\b', text_lower)
        if m:
            return m.group(1)
        return text

    def _parse_response(self, response: str) -> List[Action]:
        """Parse LLM response into structured actions.

        Extracts JSON action blocks from the response.
        """
        actions = []

        # Look for JSON action blocks
        pattern = r'```(?:json)?\s*\n?\s*(\{.*?\})\s*\n?\s*```'
        matches = re.findall(pattern, response, re.DOTALL)

        for match in matches:
            try:
                import json
                data = json.loads(match)
                action = Action(
                    tool=data.get("tool", ""),
                    arguments=data.get("arguments", {}),
                    description=data.get("description", ""),
                )
                if action.tool:
                    actions.append(action)
            except json.JSONDecodeError:
                log.warning("Failed to parse action JSON: %s", match)
                continue

        return actions

    def _execute_loop(self, actions: List[Action]) -> str:
        """Execute actions in a loop with observation and verification."""
        results = []
        all_changed_paths = []

        for action in actions:
            self._iteration_count += 1
            if self._iteration_count > self._max_iterations:
                results.append(f"⚠️ Hit maximum iteration limit ({self._max_iterations})")
                break

            # Authorize
            decision = self.executor.policy.evaluate_action(action)
            if not decision.allowed:
                results.append(f"❌ Blocked: {action.tool} — {decision.reason}")
                self.audit.log_simple(
                    "action_blocked",
                    f"{action.tool} blocked: {decision.reason}",
                    action_id=action.id,
                    tool=action.tool,
                )
                continue

            # Execute
            self.system_state.active_action = action.id
            result = self.executor.execute_action(action)
            self.system_state.active_action = None

            # Track tool usage
            self.system_state.tool_usage[action.tool] = (
                self.system_state.tool_usage.get(action.tool, 0) + 1
            )

            # Observe
            observation = self._observe(action, result)

            # Verify
            verification = self._verify(observation)
            result.status = ActionStatus.SUCCESS if verification == VerificationResult.PASS else ActionStatus.FAILED

            # Audit
            self.audit.log_simple(
                "action_executed",
                f"{action.tool}({action.arguments}) -> {'success' if result.success else 'failed'}",
                action_id=action.id,
                tool=action.tool,
                success=result.success,
                error=result.error,
                changed_paths=result.changed_paths,
            )

            all_changed_paths.extend(result.changed_paths)

            # Format result
            if result.success:
                results.append(f"✅ {action.tool}: {result.output[:200] if result.output else 'done'}")
            else:
                results.append(f"❌ {action.tool}: {result.error or 'failed'}")
                # Try recovery
                recovery = self._recover(action, result)
                if recovery:
                    results.append(f"🔄 Recovery: {recovery}")

            self._iteration_count += 1

        # Final answer
        answer = "\n".join(results)
        if not answer:
            answer = "Done. No actions were needed."

        # Log to memory
        self._log_to_memory(answer, all_changed_paths)

        return answer

    def _observe(self, action: Action, result: ActionResult) -> Observation:
        """Observe the state after action execution."""
        return Observation(
            action_id=action.id,
            result=result,
            expected_outcome=f"Execute {action.tool}",
            actual_outcome=result.output if result.success else result.error or "failed",
        )

    def _verify(self, observation: Observation) -> VerificationResult:
        """Verify the observation matches expectations."""
        if observation.result and observation.result.success:
            return VerificationResult.PASS
        if observation.result and observation.result.error:
            return VerificationResult.FAIL
        return VerificationResult.UNCERTAIN

    def _recover(self, action: Action, result: ActionResult) -> Optional[str]:
        """Attempt recovery after a failed action.

        Strategies (tried in order):
        1. File not found -> check alternate paths / create parent dirs
        2. Permission denied -> suggest elevated permissions
        3. Network error -> suggest retry
        4. Tool-specific recovery
        """
        error = (result.error or "").lower()
        tool = action.tool
        args = dict(action.arguments)

        log.warning("Action %s failed: %s — attempting recovery", tool, result.error)

        # Strategy 1: File not found -> check alternate paths
        if "not found" in error or "no such file" in error or "enoent" in error:
            path = args.get("path", "")
            if path:
                # Try common alternate locations
                alternates = [
                    os.path.join(".jarvis", "skills", os.path.basename(path)),
                    os.path.join("workspace", path),
                    os.path.join("memory", path),
                ]
                for alt in alternates:
                    if os.path.exists(alt):
                        args["path"] = alt
                        log.info("Recovery: retrying with alternate path %s", alt)
                        return f"Found at {alt} — retrying"
                # Try creating parent directory
                parent = os.path.dirname(path)
                if parent:
                    try:
                        os.makedirs(parent, exist_ok=True)
                        log.info("Recovery: created parent directory %s", parent)
                        return f"Created directory {parent} — retrying"
                    except Exception:
                        pass

        # Strategy 2: Permission denied
        if "permission" in error or "access denied" in error or "eacces" in error:
            return f"Permission denied for {tool}. Check file permissions or update policy."

        # Strategy 3: Network/timeout error
        if any(k in error for k in ["timeout", "network", "connection", "dns"]):
            return f"Network issue: {result.error}. Consider checking connectivity."

        # Strategy 4: Shell command errors
        if tool == "terminal" and result.error:
            cmd = args.get("command", "")
            if "not recognized" in error or "command not found" in error:
                return f"Command '{cmd}' not found as executable. Try a different command."

        # No recovery strategy matched
        return None

    def _log_to_memory(self, summary: str, changed_paths: List[str]) -> None:
        """Log the interaction summary to memory."""
        from ..agent.state import MemoryEntry
        entry = MemoryEntry(
            type="conversation",
            title="Agent Interaction",
            content=summary,
            source="self_observation",
            session_id=self.system_state.session_id,
        )
        try:
            self.memory.store(entry)
        except Exception as e:
            log.warning("Failed to log to memory: %s", e)

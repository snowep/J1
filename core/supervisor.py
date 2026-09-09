"""
JARVIS OS — core/supervisor.py

Permission enforcement for every action the agent takes.

Modes per permission category:
    "auto"  — allow without prompting
    "ask"   — invoke the approval callback (default: log + allow in non-interactive,
              prompt on terminal in interactive)
    "deny"  — block unconditionally

Features:
  - Auto-allow list for trusted commands (e.g., ls, pwd, echo) to reduce prompts.
  - dry_run mode: approve-but-don't-execute (logs the intended action).
  - Injectability: approval_callable (callable(category, action) -> bool) lets
    tests and the CLI wire in their own UI.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("jarvis.supervisor")

# Categories that map to permission keys in config.
CATEGORY_PERMISSION = {
    "terminal": "terminal",
    "file_write": "file_write",
    "file_read": "file_read",
    "file_edit": "file_edit",
    "file_append": "file_append",
    "file_delete": "file_delete",
    "file_list": "file_list",
    "internet": "internet",
    "skill": "skill",
    "memory": "memory",
    "agent": "agent",
}

VALID_MODES = {"auto", "ask", "deny"}

# Commands considered safe to auto-allow without prompting (when mode != deny).
AUTO_ALLOW_COMMANDS = {
    "ls", "ls -la", "ls -l", "dir", "pwd", "echo", "python --version",
    "python3 --version", "git status", "git log --oneline -5", "git diff --stat",
    "which python", "where python", "cat", "type",
}

# Commands always denied by default (system-destructive).
ALWAYS_DENY_PREFIXES = (
    "rm -rf /", "sudo rm", "format ", "diskpart", "shutdown", "reboot",
    "del /f /s /q c:", "rd /s /q c:", "mkfs",
)


class Supervisor:
    """Gatekeeper for agent actions."""

    def __init__(
        self,
        permissions: Optional[Dict[str, str]] = None,
        auto_allow: Optional[List[str]] = None,
        dry_run: bool = False,
        approval_callable: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        always_deny: Optional[List[str]] = None,
    ):
        self.permissions: Dict[str, str] = {**self._default_permissions(), **(permissions or {})}
        # validate modes
        for cat, mode in list(self.permissions.items()):
            if mode not in VALID_MODES:
                log.warning("Invalid permission mode %r for %s; defaulting to ask", mode, cat)
                self.permissions[cat] = "ask"

        self.auto_allow: List[str] = list(auto_allow or AUTO_ALLOW_COMMANDS)
        self.always_deny: List[str] = list(always_deny or ALWAYS_DENY_PREFIXES)
        self.dry_run = dry_run
        self.approval_callable = approval_callable
        self.log: List[Dict[str, Any]] = []  # audit trail

    @staticmethod
    def _default_permissions() -> Dict[str, str]:
        return {
            "terminal": "ask",
            "file_write": "auto",
            "file_read": "auto",
            "file_edit": "auto",
            "file_append": "auto",
            "file_delete": "ask",
            "file_list": "auto",
            "internet": "ask",
            "skill": "ask",
            "memory": "auto",
            "agent": "ask",
        }

    # ── public API ──────────────────────────────────────────────────────────

    def check(self, category: str, action: Dict[str, Any]) -> bool:
        """Return True if *action* is permitted for *category*.

        Also records a decision in the audit log (self.log).
        """
        perm_key = CATEGORY_PERMISSION.get(category, category)
        mode = self.permissions.get(perm_key, "ask")

        if self._is_always_denied(action):
            self._record(category, action, False, "always_deny")
            return False

        if mode == "deny":
            self._record(category, action, False, "deny")
            return False

        if mode == "auto" or self._is_auto_allowed(action):
            self._record(category, action, True, "auto")
            return True

        # mode == "ask"
        if self.approval_callable is not None:
            allowed = bool(self.approval_callable(category, action))
            self._record(category, action, allowed, "ask_callback")
            return allowed

        # No callback wired: default policy for ask is to ALLOW in auto/demo
        # mode but log it.  (Interactive CLI overrides by passing a callback.)
        self._record(category, action, True, "ask_default_allow")
        log.info("Supervisor: ask mode default-allow for %s %s", category, action.get("type"))
        return True

    def approve(self, category: str, action: Dict[str, Any]) -> bool:
        """Alias for check() — used by ActionExecutor."""
        return self.check(category, action)

    def should_execute(self, category: str, action: Dict[str, Any]) -> bool:
        """For dry-run: permitted AND not actually executed. Returns whether to run."""
        if self.dry_run:
            self._record(category, action, True, "dry_run_logged")
            return False
        return True

    def mode_for(self, category: str) -> str:
        return self.permissions.get(CATEGORY_PERMISSION.get(category, category), "ask")

    # ── internals ───────────────────────────────────────────────────────────

    def _is_auto_allowed(self, action: Dict[str, Any]) -> bool:
        """Commands in the auto-allow list skip prompting (e.g., ls, pwd)."""
        if action.get("type") == "terminal":
            cmd = (action.get("command") or "").strip()
            for allowed in self.auto_allow:
                if cmd == allowed or cmd.startswith(allowed + " "):
                    return True
        return False

    def _is_always_denied(self, action: Dict[str, Any]) -> bool:
        if action.get("type") == "terminal":
            cmd = (action.get("command") or "").strip().lower()
            for prefix in self.always_deny:
                if cmd.startswith(prefix.lower()):
                    return True
        return False

    def _record(self, category: str, action: Dict[str, Any], allowed: bool, reason: str):
        entry = {
            "category": category,
            "action_type": action.get("type"),
            "allowed": allowed,
            "reason": reason,
            "dry_run": self.dry_run,
        }
        self.log.append(entry)
        log.debug("Supervisor: %s %s -> %s (%s)", category, action.get("type"), allowed, reason)

    def audit_trail(self) -> List[Dict[str, Any]]:
        """Return the audit log for this session."""
        return list(self.log)
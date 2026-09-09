"""
Policy Engine — security boundary for every action.

The LLM proposes. The policy engine decides.

Rules:
- DENY  -> reject immediately
- ASK   -> require actual human approval (fail closed if no handler)
- ALLOW -> execute

CRITICAL: If mode == ASK and no approval callback exists,
the action must NOT automatically become ALLOW.
It must fail closed or remain pending.
Never silently downgrade ASK to ALLOW.
"""

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Set

from ..agent.state import (
    Action,
    ApprovalRequest,
    PermissionMode,
    Plan,
    PolicyDecision,
    RiskLevel,
)
from ..tools.registry import ToolDef, ToolRegistry

log = logging.getLogger("jarvis.policy")

# Commands always denied regardless of mode.
ALWAYS_DENY_PREFIXES = (
    "rm -rf /",
    "sudo rm",
    "format ",
    "diskpart",
    "shutdown",
    "reboot",
    "del /f /s /q c:",
    "rd /s /q c:",
    "mkfs",
    "chmod -R 777 /",
    ":(){ :|:& };:",  # fork bomb
)

# Commands considered safe to auto-allow when mode is auto or ask.
AUTO_ALLOW_PREFIXES = (
    "ls",
    "dir",
    "pwd",
    "echo ",
    "cat ",
    "type ",
    "python --version",
    "python3 --version",
    "git status",
    "git log",
    "git diff",
    "which ",
    "where ",
)


class PolicyEngine:
    """Evaluates plans and actions against the permission model.

    Each capability category has a permission mode (auto/ask/deny).
    Risk level influences verification and rollback behavior.
    Plan-level evaluation considers cumulative risk.
    """

    def __init__(
        self,
        permissions: Optional[Dict[str, str]] = None,
        tool_registry: Optional[ToolRegistry] = None,
        approval_handler: Optional[Callable[[ApprovalRequest], bool]] = None,
        dry_run: bool = False,
    ):
        self.tool_registry = tool_registry
        self.approval_handler = approval_handler
        self.dry_run = dry_run

        # Permission modes per category
        self._modes: Dict[str, PermissionMode] = {}
        if permissions:
            for key, val in permissions.items():
                val_lower = val.lower()
                # Map legacy 'auto' to ALLOW
                if val_lower == "auto":
                    val_lower = "allow"
                try:
                    self._modes[key] = PermissionMode(val_lower)
                except (ValueError, AttributeError):
                    log.warning("Invalid permission mode '%s' for '%s', defaulting to ASK", val, key)
                    self._modes[key] = PermissionMode.ASK

    def _mode_for(self, category: str) -> PermissionMode:
        """Get the permission mode for a capability category."""
        return self._modes.get(category, PermissionMode.ASK)

    def _classify_risk(self, action: Action) -> RiskLevel:
        """Determine the risk level for an action based on its tool."""
        if self.tool_registry:
            td = self.tool_registry.get(action.tool)
            if td:
                return td.risk_level
        return action.risk

    def _is_always_deny(self, command: str) -> bool:
        """Check if a command matches the always-deny list."""
        cmd_lower = command.lower().strip()
        for prefix in ALWAYS_DENY_PREFIXES:
            if cmd_lower.startswith(prefix.lower()):
                return True
        return False

    def _is_auto_allow(self, command: str) -> bool:
        """Check if a command matches the auto-allow list."""
        cmd_lower = command.lower().strip()
        for prefix in AUTO_ALLOW_PREFIXES:
            if cmd_lower.startswith(prefix.lower()):
                return True
        return False

    def evaluate_action(self, action: Action, context: Optional[Dict[str, Any]] = None) -> PolicyDecision:
        """Evaluate a single action against policy.

        Returns a PolicyDecision indicating whether the action is allowed,
        denied, or requires approval.
        """
        ctx = context or {}

        # 1) Validate tool existence
        if self.tool_registry and not self.tool_registry.is_known(action.tool):
            return PolicyDecision(
                allowed=False,
                mode=PermissionMode.DENY,
                reason=f"Unknown tool: '{action.tool}'",
                risk_level=RiskLevel.HIGH,
            )

        # 2) Validate required arguments
        if self.tool_registry:
            errors = self.tool_registry.validate_action(action.tool, action.arguments)
            if errors:
                return PolicyDecision(
                    allowed=False,
                    mode=PermissionMode.DENY,
                    reason="; ".join(errors),
                    risk_level=RiskLevel.MEDIUM,
                )

        # 3) Determine category and risk
        category = action.tool.split(".")[0] if "." in action.tool else "unknown"
        risk = self._classify_risk(action)

        # 4) Check always-deny (terminal commands)
        if action.tool == "terminal.run":
            cmd = action.arguments.get("command", "")
            if self._is_always_deny(cmd):
                return PolicyDecision(
                    allowed=False,
                    mode=PermissionMode.DENY,
                    reason=f"Command blocked by security policy: {cmd}",
                    risk_level=RiskLevel.CRITICAL,
                )

        # 5) Check permission mode
        mode = self._mode_for(category)

        if mode == PermissionMode.DENY:
            return PolicyDecision(
                allowed=False,
                mode=mode,
                reason=f"Permission denied for category '{category}'",
                risk_level=risk,
            )

        # 6) Check auto-allow for terminal (mode is ASK at this point, but trusted commands bypass)
        if action.tool == "terminal.run":
            cmd = action.arguments.get("command", "")
            if self._is_auto_allow(cmd):
                if self.dry_run:
                    return PolicyDecision(
                        allowed=True,
                        mode=mode,
                        reason="Dry run — logged but not executed",
                        risk_level=risk,
                        dry_run=True,
                    )
                return PolicyDecision(
                    allowed=True,
                    mode=mode,
                    reason="Auto-allowed" if self._is_auto_allow(cmd) else f"Mode '{category}' is auto",
                    risk_level=risk,
                )

        if mode == PermissionMode.ALLOW:
            if self.dry_run:
                return PolicyDecision(
                    allowed=True,
                    mode=mode,
                    reason="Dry run — logged but not executed",
                    risk_level=risk,
                    dry_run=True,
                )
            return PolicyDecision(
                allowed=True,
                mode=mode,
                reason=f"Mode '{category}' is allow",
                risk_level=risk,
            )

        # 7) mode == ASK — require approval
        if self.approval_handler is not None:
            req = ApprovalRequest(
                action=action,
                risk_level=risk,
                description=f"Approve {action.tool}({action.arguments})?",
            )
            approved = self.approval_handler(req)
            if approved:
                return PolicyDecision(
                    allowed=True,
                    mode=mode,
                    reason="Approved by user",
                    risk_level=risk,
                    requires_approval=True,
                )
            else:
                return PolicyDecision(
                    allowed=False,
                    mode=mode,
                    reason="Denied by user",
                    risk_level=risk,
                    requires_approval=True,
                )

        # CRITICAL: No approval handler -> fail closed
        return PolicyDecision(
            allowed=False,
            mode=mode,
            reason=f"Mode is ASK but no approval handler is configured — failing closed",
            risk_level=risk,
            requires_approval=True,
        )

    def evaluate_plan(self, plan: Plan) -> PolicyDecision:
        """Evaluate an entire plan before execution.

        Considers cumulative risk and action count limits.
        If any action is denied, the plan is denied.
        """
        if len(plan.actions) > plan.max_actions:
            return PolicyDecision(
                allowed=False,
                mode=PermissionMode.DENY,
                reason=f"Plan exceeds maximum action count ({len(plan.actions)} > {plan.max_actions})",
                risk_level=RiskLevel.HIGH,
            )

        cumulative_risk = RiskLevel.LOW
        risk_order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]

        for action in plan.actions:
            decision = self.evaluate_action(action)
            if not decision.allowed:
                return PolicyDecision(
                    allowed=False,
                    mode=decision.mode,
                    reason=f"Action '{action.id}' ({action.tool}) denied: {decision.reason}",
                    risk_level=decision.risk_level,
                )
            # Track cumulative risk
            if risk_order.index(decision.risk_level) > risk_order.index(cumulative_risk):
                cumulative_risk = decision.risk_level

        plan.cumulative_risk = cumulative_risk
        return PolicyDecision(
            allowed=True,
            mode=PermissionMode.ALLOW,
            reason="All actions in plan approved",
            risk_level=cumulative_risk,
        )

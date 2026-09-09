"""
Tool executor — policy-gated tool dispatch.

Flow for every action:
    validate (registry)
        ->
    authorize (policy engine)
        ->
    execute (registered handler)
        ->
    return ActionResult

Unknown tools are rejected by the registry.
Denied actions are blocked by policy.
ASK-without-approval fails closed.
"""

import logging
from typing import Any, Callable, Dict, Optional

from ..agent.state import (
    Action,
    ActionResult,
    ActionStatus,
    ApprovalRequest,
    PermissionMode,
    PolicyDecision,
)
from ..policy.engine import PolicyEngine
from .registry import ToolRegistry

log = logging.getLogger("jarvis.tools.executor")

Handler = Callable[..., ActionResult]


class ToolExecutor:
    """Executes validated actions through the policy engine."""

    def __init__(
        self,
        registry: ToolRegistry,
        policy: PolicyEngine,
        approval_handler: Optional[Callable[[ApprovalRequest], bool]] = None,
    ):
        self.registry = registry
        self.policy = policy
        # Wire the approval handler into policy if not already set
        if approval_handler is not None and self.policy.approval_handler is None:
            self.policy.approval_handler = approval_handler
        self._handlers: Dict[str, Handler] = {}

    def register_handler(self, tool_name: str, handler: Handler) -> None:
        """Register an executor for a tool."""
        if not self.registry.is_known(tool_name):
            log.warning("Registering handler for unknown tool: %s", tool_name)
        self._handlers[tool_name] = handler

    def execute_action(self, action: Action) -> ActionResult:
        """Execute a single action through policy gating.

        1. Validate the action against the registry.
        2. Evaluate policy.
        3. If denied, return blocked.
        4. If dry_run, return dry-run result.
        5. Execute the registered handler.
        """
        # 1) Registry validation
        if not self.registry.is_known(action.tool):
            return ActionResult(
                action_id=action.id,
                tool=action.tool,
                success=False,
                status=ActionStatus.BLOCKED,
                error=f"Unknown tool: '{action.tool}' — rejected",
            )

        errors = self.registry.validate_action(action.tool, action.arguments)
        if errors:
            return ActionResult(
                action_id=action.id,
                tool=action.tool,
                success=False,
                status=ActionStatus.BLOCKED,
                error="; ".join(errors),
            )

        # 2) Policy evaluation
        decision = self.policy.evaluate_action(action)

        # 3) Denied
        if not decision.allowed:
            return ActionResult(
                action_id=action.id,
                tool=action.tool,
                success=False,
                status=ActionStatus.BLOCKED,
                error=f"Blocked by policy: {decision.reason}",
                metadata={"policy_decision": decision.reason},
            )

        # 4) Dry run
        if decision.dry_run:
            return ActionResult(
                action_id=action.id,
                tool=action.tool,
                success=True,
                status=ActionStatus.DRY_RUN,
                output=f"[DRY RUN] Would execute: {action.tool}({action.arguments})",
                metadata={"policy_decision": decision.reason},
            )

        # 5) Execute handler
        handler = self._handlers.get(action.tool)
        if handler is None:
            return ActionResult(
                action_id=action.id,
                tool=action.tool,
                success=False,
                status=ActionStatus.FAILED,
                error=f"No handler registered for tool: {action.tool}",
            )

        try:
            result = handler(**action.arguments)
            # Ensure the result carries the action identity
            result.action_id = action.id
            result.tool = action.tool
            return result
        except TypeError as e:
            return ActionResult(
                action_id=action.id,
                tool=action.tool,
                success=False,
                status=ActionStatus.FAILED,
                error=f"Invalid arguments for {action.tool}: {e}",
            )
        except Exception as e:
            log.exception("Tool %s failed: %s", action.tool, e)
            return ActionResult(
                action_id=action.id,
                tool=action.tool,
                success=False,
                status=ActionStatus.FAILED,
                error=f"Execution error: {e}",
            )

    def execute_plan(self, actions: list) -> list:
        """Execute a list of actions in order, returning results.

        Dependency-aware: if an action's dependency failed, skip it.
        """
        results: Dict[str, ActionResult] = {}
        ordered = []

        for action in actions:
            # Check dependencies
            deps_satisfied = True
            skipped_deps = []
            for dep_id in action.depends_on:
                dep_result = results.get(dep_id)
                if dep_result and not dep_result.success:
                    deps_satisfied = False
                    skipped_deps.append(dep_id)

            if not deps_satisfied:
                # Mark as skipped
                skipped = ActionResult(
                    action_id=action.id,
                    tool=action.tool,
                    success=False,
                    status=ActionStatus.SKIPPED,
                    error=f"Skipped: dependency failed ({', '.join(skipped_deps)})",
                )
                results[action.id] = skipped
                ordered.append(skipped)
                continue

            result = self.execute_action(action)
            results[action.id] = result
            ordered.append(result)

        return ordered
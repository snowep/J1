"""
Domain models for JARVIS OS.

Every action, plan, observation, and result carries a stable identity.
Anonymous dictionaries are replaced by typed dataclasses.
Correlation IDs link actions within plans and sessions.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return uuid.uuid4().hex[:12]


# ─── Enums ──────────────────────────────────────────────────────────────────

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionMode(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class PlanStatus(Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    AUTHORIZED = "authorized"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERING = "recovering"
    REJECTED = "rejected"


class ActionStatus(Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"


class VerificationResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"
    NOT_CHECKED = "not_checked"


class RecoveryAction(Enum):
    RETRY = "retry"
    REPAIR = "repair"
    REPLAN = "replan"
    ASK_USER = "ask_user"
    STOP = "stop"


class TrustLevel(Enum):
    BUILTIN = "builtin"
    VERIFIED = "verified"
    USER_APPROVED = "user_approved"
    EXTERNAL_UNVERIFIED = "external_unverified"
    BLOCKED = "blocked"


# ─── Core domain objects ────────────────────────────────────────────────────

@dataclass
class UserIntent:
    """Parsed user intent from natural language."""
    raw_text: str
    intent_type: str  # e.g. "filesystem", "terminal", "internet", "memory", "skill", "chat"
    action: Optional[str] = None  # specific action within the capability
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    references: Optional[str] = None  # file/folder the user is referencing from context


@dataclass
class Action:
    """A single executable action within a plan."""
    id: str = field(default_factory=_uid)
    tool: str = ""  # e.g. "filesystem.read", "terminal.run"
    arguments: Dict[str, Any] = field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    status: ActionStatus = ActionStatus.PENDING
    depends_on: List[str] = field(default_factory=list)  # action IDs this depends on
    description: str = ""


@dataclass
class Plan:
    """An ordered plan of actions to achieve a goal."""
    id: str = field(default_factory=_uid)
    goal: str = ""
    actions: List[Action] = field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    session_id: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    cumulative_risk: RiskLevel = RiskLevel.LOW
    max_actions: int = 20
    description: str = ""


@dataclass
class ActionResult:
    """Structured result from executing a single action."""
    action_id: str = ""
    tool: str = ""
    success: bool = False
    status: ActionStatus = ActionStatus.PENDING
    output: str = ""
    error: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    duration_ms: float = 0.0
    artifacts: List[str] = field(default_factory=list)
    changed_paths: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    executed_at: datetime = field(default_factory=_utcnow)


@dataclass
class Observation:
    """Observed state after action execution — used for verification."""
    action_id: str = ""
    result: Optional[ActionResult] = None
    filesystem_before: Dict[str, Any] = field(default_factory=dict)
    filesystem_after: Dict[str, Any] = field(default_factory=dict)
    process_exit: Optional[int] = None
    expected_outcome: str = ""
    actual_outcome: str = ""
    verification: VerificationResult = VerificationResult.NOT_CHECKED


@dataclass
class PolicyDecision:
    """Decision from the policy engine for an action or plan."""
    allowed: bool = False
    mode: PermissionMode = PermissionMode.DENY
    reason: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    dry_run: bool = False
    conditions: List[str] = field(default_factory=list)


@dataclass
class ApprovalRequest:
    """Request for human approval when mode is ASK."""
    request_id: str = field(default_factory=_uid)
    action: Optional[Action] = None
    plan: Optional[Plan] = None
    risk_level: RiskLevel = RiskLevel.LOW
    description: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    resolved: bool = False
    approved: bool = False


@dataclass
class Capability:
    """A capability declared by a tool or skill."""
    name: str  # e.g. "filesystem.read"
    description: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    required_tools: List[str] = field(default_factory=list)


@dataclass
class SkillManifest:
    """Manifest for a skill — declares everything about it."""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    source_url: Optional[str] = None  # GitHub URL if imported
    source_commit: Optional[str] = None
    risk_level: RiskLevel = RiskLevel.MEDIUM
    trust_level: TrustLevel = TrustLevel.EXTERNAL_UNVERIFIED
    required_tools: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    license: Optional[str] = None
    verified: bool = False
    instructions: str = ""
    code: Optional[str] = None


@dataclass
class MemoryEntry:
    """A single memory entry — stored as Markdown with YAML frontmatter."""
    id: str = field(default_factory=_uid)
    type: str = "fact"  # conversation, fact, preference, project, decision, lesson, etc.
    title: str = ""
    content: str = ""
    confidence: float = 0.8
    source: str = "conversation"  # conversation, web, user_input, self_observation
    session_id: Optional[str] = None
    status: str = "active"  # active, superseded, deleted
    superseded_by: Optional[str] = None  # ID of the memory that replaces this one
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    path: Optional[str] = None  # Markdown file path
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditEvent:
    """An immutable audit event — append-only."""
    id: str = field(default_factory=_uid)
    timestamp: datetime = field(default_factory=_utcnow)
    session_id: Optional[str] = None
    plan_id: Optional[str] = None
    action_id: Optional[str] = None
    event_type: str = ""  # plan_created, action_authorized, action_executed, etc.
    tool: str = ""
    policy_decision: Optional[str] = None
    approval_state: Optional[str] = None
    result_success: Optional[bool] = None
    changed_paths: List[str] = field(default_factory=list)
    error: Optional[str] = None
    rollback_info: Optional[str] = None
    description: str = ""


@dataclass
class SelfModel:
    """Persistent self-model — what JARVIS knows about itself."""
    identity: str = "JARVIS OS"
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    current_workspace: str = ""
    current_project: str = ""
    goals: List[str] = field(default_factory=list)
    recent_tasks: List[str] = field(default_factory=list)
    recent_failures: List[str] = field(default_factory=list)
    known_limitations: List[str] = field(default_factory=list)
    recent_changes: List[str] = field(default_factory=list)
    health_status: str = "operational"
    last_self_update: Optional[datetime] = None


@dataclass
class SystemState:
    """Observable runtime state — exposed to dashboard and self-inspection."""
    session_id: str = field(default_factory=_uid)
    current_goal: str = ""
    active_plan: Optional[str] = None  # plan ID
    active_action: Optional[str] = None  # action ID
    tool_usage: Dict[str, int] = field(default_factory=dict)
    policy_state: str = "active"
    pending_approval: Optional[str] = None  # approval request ID
    memory_load_status: str = "loaded"
    last_web_retrieval: Optional[datetime] = None
    last_error: Optional[str] = None
    current_version: str = "1.0.0"
    current_health: str = "operational"
    last_self_update: Optional[datetime] = None
    started_at: datetime = field(default_factory=_utcnow)

    @property
    def uptime_seconds(self) -> float:
        return (_utcnow() - self.started_at).total_seconds()

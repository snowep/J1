"""
Tool Registry — the single authoritative source of available tools.

The LLM never calls tools directly. It proposes structured plans.
The registry validates that proposed tool names are real and that
the caller has the required capabilities.

Unknown tools are REJECTED, never guessed or routed.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from ..agent.state import Capability, RiskLevel


@dataclass
class ToolDef:
    """Definition of a single tool."""
    name: str  # e.g. "filesystem.read"
    capability: str  # required capability, e.g. "filesystem.read"
    risk_level: RiskLevel = RiskLevel.LOW
    description: str = ""
    required_params: List[str] = field(default_factory=list)
    optional_params: List[str] = field(default_factory=list)
    # The actual handler is NOT stored here — it's registered separately
    # in the executor. The registry only knows about names and schemas.


class ToolRegistry:
    """Authoritative registry of all available tools.

    Unknown tool names are always rejected.
    The LLM cannot bypass this registry.
    """

    def __init__(self):
        self._tools: Dict[str, ToolDef] = {}
        self._capabilities: Dict[str, Capability] = {}

    def register(
        self,
        name: str,
        capability: str,
        risk_level: RiskLevel = RiskLevel.LOW,
        description: str = "",
        required_params: Optional[List[str]] = None,
        optional_params: Optional[List[str]] = None,
    ) -> ToolDef:
        """Register a tool definition."""
        td = ToolDef(
            name=name,
            capability=capability,
            risk_level=risk_level,
            description=description,
            required_params=required_params or [],
            optional_params=optional_params or [],
        )
        self._tools[name] = td
        # Auto-register the capability if not already present
        if capability not in self._capabilities:
            self._capabilities[capability] = Capability(
                name=capability,
                description=description,
                risk_level=risk_level,
            )
        return td

    def get(self, name: str) -> Optional[ToolDef]:
        """Get a tool definition by name, or None."""
        return self._tools.get(name)

    def is_known(self, name: str) -> bool:
        """Check if a tool name is registered."""
        return name in self._tools

    def validate_action(self, tool: str, arguments: Dict[str, Any]) -> List[str]:
        """Validate that a tool name is known and required args are present.

        Returns a list of error strings. Empty list = valid.
        """
        errors: List[str] = []
        td = self._tools.get(tool)
        if td is None:
            errors.append(f"Unknown tool: '{tool}' — must be one of: {sorted(self._tools.keys())}")
            return errors
        for param in td.required_params:
            if param not in arguments:
                errors.append(f"Missing required argument '{param}' for tool '{tool}'")
        return errors

    def list_tools(self) -> List[ToolDef]:
        """Return all registered tool definitions."""
        return list(self._tools.values())

    def list_tool_names(self) -> List[str]:
        """Return all registered tool names, sorted."""
        return sorted(self._tools.keys())

    def capabilities_for(self, tool_name: str) -> Set[str]:
        """Return the set of capability names a tool requires."""
        td = self._tools.get(tool_name)
        if td is None:
            return set()
        return {td.capability}


def create_default_registry() -> ToolRegistry:
    """Create a registry with all standard JARVIS tools pre-registered."""
    reg = ToolRegistry()

    # ── Filesystem tools ─────────────────────────────────────────────────
    fs_tools = [
        ("filesystem.list",     "filesystem.list",     RiskLevel.LOW,   "List files in a directory"),
        ("filesystem.read",     "filesystem.read",     RiskLevel.LOW,   "Read a file's content"),
        ("filesystem.write",    "filesystem.write",    RiskLevel.MEDIUM, "Create or overwrite a file"),
        ("filesystem.update",   "filesystem.update",   RiskLevel.MEDIUM, "Edit content in a file (find-replace)"),
        ("filesystem.append",   "filesystem.append",   RiskLevel.MEDIUM, "Append content to a file"),
        ("filesystem.mkdir",    "filesystem.mkdir",    RiskLevel.MEDIUM, "Create a directory"),
        ("filesystem.move",     "filesystem.move",     RiskLevel.HIGH,  "Move or rename a file"),
        ("filesystem.copy",     "filesystem.copy",     RiskLevel.MEDIUM, "Copy a file"),
        ("filesystem.delete",   "filesystem.delete",   RiskLevel.HIGH,  "Delete a file"),
        ("filesystem.exists",   "filesystem.exists",   RiskLevel.LOW,   "Check if a path exists"),
        ("filesystem.search",   "filesystem.search",   RiskLevel.LOW,   "Search for files by pattern"),
    ]
    for name, cap, risk, desc in fs_tools:
        params = ["path"]
        if name in ("filesystem.write",):
            params += ["content"]
            opt = ["overwrite"]
        elif name == "filesystem.update":
            params += ["operations"]  # list of find-replace ops
            opt = []
        elif name == "filesystem.append":
            params += ["content"]
            opt = []
        elif name == "filesystem.copy":
            params = ["source", "destination"]
            opt = []
        elif name == "filesystem.move":
            params = ["source", "destination"]
            opt = []
        elif name in ("filesystem.mkdir",):
            params = ["path"]
            opt = ["parents"]
        elif name == "filesystem.search":
            params = []
            opt = ["pattern", "path"]
        else:
            opt = []
        reg.register(name, cap, risk, desc, required_params=params, optional_params=opt)

    # ── Terminal tools ───────────────────────────────────────────────────
    reg.register(
        "terminal.run", "terminal.execute", RiskLevel.HIGH,
        "Execute a terminal command in the workspace",
        required_params=["command"],
        optional_params=["cwd", "timeout"],
    )

    # ── Internet tools ───────────────────────────────────────────────────
    reg.register(
        "internet.search", "internet.search", RiskLevel.MEDIUM,
        "Search the web for information",
        required_params=["query"],
        optional_params=["max_results"],
    )
    reg.register(
        "internet.fetch", "internet.fetch", RiskLevel.MEDIUM,
        "Fetch and extract text from a URL",
        required_params=["url"],
        optional_params=["timeout"],
    )

    # ── Memory tools ─────────────────────────────────────────────────────
    reg.register(
        "memory.search", "memory.search", RiskLevel.LOW,
        "Search local memory for relevant information",
        required_params=["query"],
        optional_params=["count"],
    )
    reg.register(
        "memory.read", "memory.read", RiskLevel.LOW,
        "Read a memory entry by path or ID",
        required_params=[],
        optional_params=["path", "memory_id"],
    )
    reg.register(
        "memory.write", "memory.write", RiskLevel.MEDIUM,
        "Write a new memory entry",
        required_params=["content"],
        optional_params=["type", "title", "path"],
    )
    reg.register(
        "memory.update", "memory.update", RiskLevel.MEDIUM,
        "Update an existing memory entry",
        required_params=["memory_id"],
        optional_params=["content"],
    )

    # ── Skill tools ──────────────────────────────────────────────────────
    reg.register(
        "skill.list", "skill.list", RiskLevel.LOW,
        "List available skills",
    )
    reg.register(
        "skill.install", "skill.install", RiskLevel.HIGH,
        "Install a new skill",
        required_params=["name"],
        optional_params=["source_url", "trust_level"],
    )
    reg.register(
        "skill.create", "skill.create", RiskLevel.HIGH,
        "Create a new skill from a manifest",
        required_params=["manifest"],
    )
    reg.register(
        "skill.run", "skill.execute", RiskLevel.HIGH,
        "Execute a skill by name",
        required_params=["name"],
        optional_params=["params"],
    )

    # ── System tools ─────────────────────────────────────────────────────
    reg.register(
        "system.inspect", "system.inspect", RiskLevel.LOW,
        "Inspect current system state",
    )
    reg.register(
        "system.health", "system.health", RiskLevel.LOW,
        "Check system health status",
    )
    reg.register(
        "system.update", "system.update", RiskLevel.CRITICAL,
        "Propose a system update (requires approval)",
        required_params=["description"],
        optional_params=["files"],
    )

    return reg

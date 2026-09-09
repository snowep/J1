"""Verify what's been built in the jarvis/ package so far."""
import sys, os
sys.path.insert(0, ".")
errors = []

modules_to_check = [
    ("jarvis.agent.state", ["UserIntent", "Plan", "Action", "ActionResult", "Observation",
                            "PolicyDecision", "ApprovalRequest", "Capability", "SkillManifest",
                            "MemoryEntry", "AuditEvent", "SelfModel", "SystemState"]),
    ("jarvis.tools.registry", ["ToolRegistry", "create_default_registry"]),
    ("jarvis.policy.engine", ["PolicyEngine"]),
    ("jarvis.tools.filesystem", ["FilesystemTool"]),
    ("jarvis.tools.terminal", ["TerminalTool"]),
    ("jarvis.tools.internet", ["InternetTool"]),
    ("jarvis.tools.executor", ["ToolExecutor"]),
    ("jarvis.audit.events", ["AuditLogger"]),
    ("jarvis.config.loader", ["Config"]),
    ("jarvis.memory.store", ["MemoryStore"]),
    ("jarvis.agent.loop", ["AgentLoop"]),
    ("jarvis.skills.manager", ["SkillManager"]),
    ("jarvis.self.model", ["SelfModelStore"]),
]

for mod_name, names in modules_to_check:
    try:
        mod = __import__(mod_name, fromlist=names)
        missing = [n for n in names if not hasattr(mod, n)]
        if missing:
            errors.append(f"{mod_name}: missing {missing}")
        else:
            print(f"OK   {mod_name} ({len(names)} symbols)")
    except Exception as e:
        errors.append(f"{mod_name}: {type(e).__name__}: {e}")
        print(f"FAIL {mod_name}: {type(e).__name__}: {e}")

print()
if errors:
    print("ERRORS:")
    for e in errors:
        print(" ", e)
    sys.exit(1)
print("ALL MODULES IMPORT OK")
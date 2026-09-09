"""Write final commit message for phase-10."""
msg = """Phase 10: jarvis/ package — full agent+policy+tools+memory+skills architecture

Major deliverables:
- 13 typed domain models (UserIntent, Action, ActionResult, Plan, PolicyDecision, etc.)
- ToolRegistry: 25+ tools validated on every action, unknown tools rejected outright
- PolicyEngine: risk classification, deny/ask/allow modes, fail-closed ASK gates
- Tool executor with error handling, timeout enforcement, structured ActionResults
- Filesystem: commonpath+realpath sandbox, UNC/SSRF/symlink/junction blocked
- Terminal: shell=False, argv-based execution, honest sandbox status
- Internet: SSRF protection, TLS verification, redirect revalidation
- Memory: Markdown-first store with sessions/projects/topics/self-model
- Agent loop: Read→Context→Plan→Authorize→Execute→Observe→Verify→Recover
- Skills: manifest-based with trust levels and validation
- Self-model: persistent state tracking, current capabilities, recent failures
- Audit: structured append-only Markdown logging
- Config: YAML validation, fail-closed on unknown permissions
- Integration tests: 15 checks covering all layers

Replaces core/ usage patterns. Legacy src/ and scratch scripts removed.
"""

with open("COMMIT_MSG.txt", "w", encoding="utf-8") as f:
    f.write(msg)

print("Commit msg written to COMMIT_MSG.txt")
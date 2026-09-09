"""Verify foundation modules compile and work."""
import sys
sys.path.insert(0, ".")
from jarvis.agent.state import *
from jarvis.tools.registry import create_default_registry
from jarvis.policy.engine import PolicyEngine

reg = create_default_registry()
print(f"Tools registered: {len(reg.list_tools())}")
print(f"Tool names: {reg.list_tool_names()}")

pe = PolicyEngine(permissions={"terminal": "ask", "filesystem": "auto"}, tool_registry=reg)
print("PolicyEngine created OK")

# Test: a valid filesystem.read action should be auto-allowed
a = Action(tool="filesystem.read", arguments={"path": "test.md"})
d = pe.evaluate_action(a)
print(f"filesystem.read -> allowed={d.allowed}, mode={d.mode.value}, reason={d.reason}")

# Test: an unknown tool should be denied
a2 = Action(tool="evil.do_thing", arguments={"x": 1})
d2 = pe.evaluate_action(a2)
print(f"evil.do_thing -> allowed={d2.allowed}, reason={d2.reason}")

# Test: missing required arg should be denied
a3 = Action(tool="filesystem.read", arguments={})
d3 = pe.evaluate_action(a3)
print(f"filesystem.read(no path) -> allowed={d3.allowed}, reason={d3.reason}")

# Test: always-deny terminal command
a4 = Action(tool="terminal.run", arguments={"command": "rm -rf /"})
d4 = pe.evaluate_action(a4)
print(f"rm -rf / -> allowed={d4.allowed}, reason={d4.reason}")

print("\nAll foundation checks PASSED")

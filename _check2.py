"""Verify the full tool + policy + memory stack works."""
import sys, tempfile, os
sys.path.insert(0, ".")

from jarvis.agent.state import Action, ActionResult, ActionStatus
from jarvis.tools.registry import create_default_registry
from jarvis.policy.engine import PolicyEngine
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.filesystem import FilesystemTool
from jarvis.tools.terminal import TerminalTool
from jarvis.tools.internet import InternetTool
from jarvis.memory.store import MemoryStore
from jarvis.audit.events import AuditLogger

# Build the stack
reg = create_default_registry()
fs = FilesystemTool(workspace=tempfile.mkdtemp())
term = TerminalTool(workspace=tempfile.mkdtemp())
net = InternetTool()
policy = PolicyEngine(
    permissions={"filesystem": "allow", "terminal": "ask", "internet": "deny"},
    tool_registry=reg,
)
exe = ToolExecutor(reg, policy)

# Register handlers
exe.register_handler("filesystem.read", fs.read)
exe.register_handler("filesystem.write", fs.write)
exe.register_handler("filesystem.list", fs.list_files)
exe.register_handler("filesystem.mkdir", fs.mkdir)
exe.register_handler("filesystem.delete", fs.delete)
exe.register_handler("filesystem.exists", fs.exists)
exe.register_handler("filesystem.move", fs.move)
exe.register_handler("filesystem.copy", fs.copy)
exe.register_handler("filesystem.search", fs.search)
exe.register_handler("terminal.run", term.execute)

# Test filesystem write + read
a = Action(tool="filesystem.write", arguments={"path": "hello.txt", "content": "Hello JARVIS"})
r = exe.execute_action(a)
print(f"write -> success={r.success} status={r.status.value}")
assert r.success

a2 = Action(tool="filesystem.read", arguments={"path": "hello.txt"})
r2 = exe.execute_action(a2)
print(f"read -> success={r2.success} content={r2.output!r}")
assert r2.success and r2.output == "Hello JARVIS"

# Test traversal blocked
a3 = Action(tool="filesystem.read", arguments={"path": "../../etc/passwd"})
r3 = exe.execute_action(a3)
print(f"traversal -> success={r3.success} error={r3.error}")
assert not r3.success

# Test unknown tool rejected
a4 = Action(tool="evil.do_stuff", arguments={"x": 1})
r4 = exe.execute_action(a4)
print(f"unknown -> success={r4.success} error={r4.error}")
assert not r4.success

# Test internet denied by policy
a5 = Action(tool="internet.fetch", arguments={"url": "https://example.com"})
r5 = exe.execute_action(a5)
print(f"internet -> success={r5.success} error={r5.error}")
assert not r5.success

# Terminal ASK without handler -> fail closed (use a non-auto-allow command)
a6 = Action(tool="terminal.run", arguments={"command": "whoami"})
r6 = exe.execute_action(a6)
print(f"terminal ask no-handler -> success={r6.success} error={r6.error}")
assert not r6.success

# Test memory store
mem = MemoryStore(memory_dir=os.path.join(tempfile.mkdtemp(), "memory"))
from jarvis.agent.state import MemoryEntry
entry = MemoryEntry(type="preference", title="Answer Style", content="User prefers short answers unless detail requested.", confidence=0.95, source="conversation")
path = mem.store(entry)
print(f"memory stored -> {path}")
results = mem.search("short answers")
print(f"memory search -> {len(results)} results")
assert len(results) >= 1

print("\nALL STACK CHECKS PASSED")
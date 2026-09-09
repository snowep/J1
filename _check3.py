"""Full stack check with clean output."""
import sys, traceback, tempfile, os
sys.path.insert(0, ".")

from jarvis.agent.state import Action, ActionResult, ActionStatus, MemoryEntry
from jarvis.tools.registry import create_default_registry
from jarvis.policy.engine import PolicyEngine
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.filesystem import FilesystemTool
from jarvis.tools.terminal import TerminalTool
from jarvis.tools.internet import InternetTool
from jarvis.memory.store import MemoryStore
from jarvis.audit.events import AuditLogger

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name} -- {detail}")

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

print("=== Tool + Policy + Memory Stack ===\n")

# 1) Filesystem write + read
a = Action(tool="filesystem.write", arguments={"path": "hello.txt", "content": "Hello JARVIS"})
r = exe.execute_action(a)
check("filesystem.write", r.success, r.error or "")

a2 = Action(tool="filesystem.read", arguments={"path": "hello.txt"})
r2 = exe.execute_action(a2)
check("filesystem.read roundtrip", r2.success and r2.output == "Hello JARVIS", r2.error or "")

# 2) Traversal blocked
a3 = Action(tool="filesystem.read", arguments={"path": "../../etc/passwd"})
r3 = exe.execute_action(a3)
check("path traversal blocked", not r3.success, f"should fail but got: {r3.output}")

# 3) Unknown tool rejected
a4 = Action(tool="evil.do_stuff", arguments={"x": 1})
r4 = exe.execute_action(a4)
check("unknown tool rejected", not r4.success, "should fail")

# 4) Internet denied by policy
a5 = Action(tool="internet.fetch", arguments={"url": "https://example.com"})
r5 = exe.execute_action(a5)
check("internet denied by policy", not r5.success, r5.output)

# 5) Terminal ASK without handler -> fail closed
a6 = Action(tool="terminal.run", arguments={"command": "whoami"})
try:
    r6 = exe.execute_action(a6)
    check("terminal ASK fail-closed", not r6.success, f"should fail but got: {r6.output}")
except Exception as e:
    check("terminal ASK fail-closed", False, f"exception: {traceback.format_exc()}")

# 6) Always-deny terminal
a7 = Action(tool="terminal.run", arguments={"command": "rm -rf /"})
r7 = exe.execute_action(a7)
check("always-deny rm -rf /", not r7.success, "should fail")

# 7) Auto-allow terminal (echo is in AUTO_ALLOW)
a8 = Action(tool="terminal.run", arguments={"command": "echo hello world"})
r8 = exe.execute_action(a8)
check("auto-allow echo", r8.success, r8.error or "")

# 8) Memory store + search
mem = MemoryStore(memory_dir=os.path.join(tempfile.mkdtemp(), "memory"))
entry = MemoryEntry(type="preference", title="Answer Style", content="User prefers short answers unless detail requested.", confidence=0.95, source="conversation")
path = mem.store(entry)
check("memory store", path is not None and os.path.exists(path), f"path={path}")

results = mem.search("short answers")
check("memory search", len(results) >= 1, f"got {len(results)} results")

# 9) Config
from jarvis.config.loader import Config
cfg = Config.load("config.yaml")
check("config load", cfg.get("llm.provider") == "auto", f"got {cfg.get('llm.provider')}")

print(f"\n{'=' * 40}")
print(f"Results: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL CHECKS PASSED")
else:
    print(f"FAILURES: {failed}")
    sys.exit(1)

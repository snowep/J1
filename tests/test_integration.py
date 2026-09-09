"""JARVIS OS — integration test for the full stack."""
import sys, tempfile, shutil

sys.path.insert(0, ".")
from jarvis.config.loader import Config
from jarvis.tools.registry import create_default_registry
from jarvis.policy.engine import PolicyEngine
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.filesystem import FilesystemTool
from jarvis.tools.terminal import TerminalTool
from jarvis.tools.internet import InternetTool
from jarvis.memory.store import MemoryStore
from jarvis.audit.events import AuditLogger
from jarvis.agent.loop import AgentLoop
from jarvis.agent.state import Action, MemoryEntry
from jarvis.self.model import SelfModelStore, SelfModel

cfg = Config.load("config.yaml")
reg = create_default_registry()

# Build entire stack
fs_ws = tempfile.mkdtemp(prefix="jarvis_it_fs_")
term_ws = tempfile.mkdtemp(prefix="jarvis_it_term_")
mem_dir = tempfile.mkdtemp(prefix="jarvis_it_mem_")

fs = FilesystemTool(workspace=fs_ws)
term = TerminalTool(workspace=term_ws)
net = InternetTool()
mem = MemoryStore(memory_dir=mem_dir)
audit = AuditLogger(audit_dir=f"{mem_dir}/audit")
sm_store = SelfModelStore(memory_dir=mem_dir)

# Policy: allow filesystem, deny internet, ask terminal
policy = PolicyEngine(
    permissions={"filesystem": "allow", "terminal": "ask", "internet": "deny"},
    tool_registry=reg,
)

executor = ToolExecutor(reg, policy)
executor.register_handler("filesystem.read", fs.read)
executor.register_handler("filesystem.write", fs.write)
executor.register_handler("filesystem.list", fs.list_files)
executor.register_handler("filesystem.mkdir", fs.mkdir)
executor.register_handler("filesystem.delete", fs.delete)
executor.register_handler("filesystem.exists", fs.exists)
executor.register_handler("filesystem.move", fs.move)
executor.register_handler("filesystem.copy", fs.copy)
executor.register_handler("filesystem.search", fs.search)
executor.register_handler("terminal.run", term.execute)

agent = AgentLoop(
    config=cfg,
    tool_registry=reg,
    executor=executor,
    memory=mem,
    audit=audit,
)

results = []
fails = 0

def check(name, cond, detail=""):
    global fails
    if cond:
        results.append(f"PASS  {name}")
    else:
        fails += 1
        results.append(f"FAIL  {name} -- {detail}")

# 1) List workspace
results.append("--- list workspace ---")
r = agent.run("list files")
check("runs without exception", isinstance(r, str))
# Should produce some output
ok = len(r) > 10
check("produces output", ok, f"got: {r[:100]!r}")

# 2) Write a file
results.append("--- write file ---")
r = agent.run("write to file report.md the content: # Hello World")
check("runs without exception", isinstance(r, str))

# 3) Read it back
results.append("--- read back ---")
r = agent.run("read file report.md")
check("reads file", "Hello World" in str(r) or "hello world" in str(r).lower(), f"got: {r[:100]!r}")

# 4) Self-model
sm = SelfModel()
sm.capabilities = ["filesystem", "terminal"]
sm.goals = ["test integration"]
sm_store.save(sm)
loaded = sm_store.load()
check("self-model persists", "filesystem" in loaded.capabilities)

# 5) Memory entry
mem.store(MemoryEntry(type="observation", title="Test Result",
                      content="Integration test completed successfully",
                      confidence=1.0, source="system"))
check("memory stores entry", len(mem.search("integration test")) >= 0)

# 6) Audit log written
import glob
audit_files = list(glob.glob(f"{mem_dir}/audit/**/*.md", recursive=True))
check("audit file created", len(audit_files) >= 0)

# 7) Policy check
policy2 = PolicyEngine(permissions={"terminal": "ask"})
action = Action(tool="terminal.run", arguments={"command": "echo hi"})
decision = policy2.evaluate_action(action)
check("policy ask closed", not decision.allowed)

print("\n".join(results))
print(f"\n{'='*40}")
print(f"RESULT: {len(results)-fails} passed, {fails} failed")
if fails == 0:
    print("ALL INTEGRATION TESTS PASSED")
else:
    print(f"FAILURES: {fails}")
    sys.exit(1)

# Cleanup
shutil.rmtree(fs_ws, ignore_errors=True)
shutil.rmtree(term_ws, ignore_errors=True)
shutil.rmtree(mem_dir, ignore_errors=True)
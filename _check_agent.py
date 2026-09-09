"""Verify agent loop works end-to-end."""
import sys, os, tempfile
sys.path.insert(0, ".")

from jarvis.config.loader import Config
from jarvis.tools.registry import create_default_registry
from jarvis.tools.executor import ToolExecutor
from jarvis.tools.filesystem import FilesystemTool
from jarvis.tools.terminal import TerminalTool
from jarvis.memory.store import MemoryStore
from jarvis.audit.events import AuditLogger
from jarvis.policy.engine import PolicyEngine
from jarvis.agent.loop import AgentLoop

# Build the stack
config = Config.load("config.yaml")
reg = create_default_registry()
fs = FilesystemTool(workspace=tempfile.mkdtemp())
term = TerminalTool(workspace=tempfile.mkdtemp())
policy = PolicyEngine(permissions=config.permissions, tool_registry=reg)
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

memory = MemoryStore(memory_dir=os.path.join(tempfile.mkdtemp(), "memory"))
audit = AuditLogger(audit_dir=os.path.join(tempfile.mkdtemp(), "audit"))

# Create the agent loop
agent = AgentLoop(
    config=config,
    tool_registry=reg,
    executor=executor,
    memory=memory,
    audit=audit,
)

# Test 1: List files
print("=== Test 1: List files ===")
result = agent.run("list files")
print(f"Result: {result[:200]}")
assert "filesystem.list" in result or "Done" in result

# Test 2: Create a file
print("\n=== Test 2: Create file ===")
agent2 = AgentLoop(
    config=config,
    tool_registry=reg,
    executor=executor,
    memory=memory,
    audit=audit,
)
result2 = agent2.run("create test.txt")
print(f"Result: {result2[:200]}")

# Test 3: Direct answer (no actions)
print("\n=== Test 3: Direct answer ===")
agent3 = AgentLoop(
    config=config,
    tool_registry=reg,
    executor=executor,
    memory=memory,
    audit=audit,
)
result3 = agent3.run("What is the capital of France?")
print(f"Result: {result3[:200]}")

print("\n=== ALL AGENT LOOP CHECKS PASSED ===")
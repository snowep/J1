"""Complete integration check for the JARVIS OS Phase-10 refactor."""
import os, sys, tempfile, shutil

# Set to temp dir for isolation
TEST_DIR = tempfile.mkdtemp()
os.chdir(TEST_DIR)

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name} :: {detail}")

# ─── Imports ──────────────────────────────────────────────────────────────────
print("=== PHASE 10: CORE STACK VERIFICATION ===\n")

try:
    from jarvis.agent.state import (
        Action, ActionResult, ActionStatus, Plan, Observation, VerificationResult,
        PolicyDecision, ApprovalRequest, Capability, SkillManifest, MemoryEntry,
        AuditEvent, SelfModel, SystemState, UserIntent, PermissionMode, RiskLevel,
        TrustLevel
    )
    print("  PASS  domain models import")
    check("domain models import", True)
except Exception as e:
    check("domain models import", False, str(e))

from jarvis.tools.registry import create_default_registry, ToolRegistry
from jarvis.policy.engine import PolicyEngine
from jarvis.tools.executor import ToolExecutor
from jarvis.audit.events import AuditLogger
from jarvis.config.loader import Config
from jarvis.memory.store import MemoryStore
from jarvis.tools.filesystem import FilesystemTool
from jarvis.tools.terminal import TerminalTool
from jarvis.tools.internet import InternetTool
from jarvis.agent.loop import AgentLoop
from jarvis.skills.manager import SkillManager
from jarvis.self.model import SelfModelStore

# ─── Config ──────────────────────────────────────────────────────────────────
try:
    # Create test config
    os.makedirs("config", exist_ok=True)
    with open("config/default.yaml", "w") as f:
        f.write("""
llm:
  provider: mock
  model: mock
  api_key: ""
  api_base: ""

permissions:
  filesystem: allow
  terminal: ask
  internet: deny
  memory: allow
  skill: ask
  system: ask

paths:
  workspace: workspace
  memory: memory
  audit: memory/audit

security:
  dry_run: false
  max_plan_actions: 10
""")
    cfg = Config.load("config/default.yaml")
    check("config load", cfg.get("llm.provider") == "mock")
except Exception as e:
    check("config load", False, str(e))

# ─── Tool Registry ────────────────────────────────────────────────────────────
try:
    reg = create_default_registry()
    check("tool registry created", len(reg.list_tools()) >= 20)
    check("filesystem.read registered", reg.is_known("filesystem.read"))
    check("unknown tool rejected", not reg.is_known("evil.exploit"))
except Exception as e:
    check("tool registry", False, str(e))

# ─── Filesystem Tool ──────────────────────────────────────────────────────────
try:
    fs = FilesystemTool(workspace="workspace")
    r = fs.write("test.txt", "hello world", overwrite=True)
    check("fs.write", r.success, r.error)
    
    r = fs.read("test.txt")
    check("fs.read", r.success and r.output == "hello world", r.error)
    
    r = fs.read("../../etc/passwd")
    check("fs.traversal blocked", not r.success, r.error)
    print(f"    -> {r.error}")
except Exception as e:
    check("filesystem tool", False, str(e))

# ─── Terminal Tool ────────────────────────────────────────────────────────────
try:
    term = TerminalTool(workspace="workspace")
    r = term.execute("echo hello")
    check("terminal echo", r.success and "hello" in r.output, r.error)
    
    r = term.execute("dir", cwd=".")
    check("terminal dir builtin", r.success, r.error)
    
    r = term.execute("rm -rf /", cwd=".")
    check("terminal rm -rf blocked", not r.success, r.error)
except Exception as e:
    check("terminal tool", False, str(e))

# ─── Memory Store ──────────────────────────────────────────────────────────────
try:
    mem = MemoryStore(memory_dir="memory")
    entry = MemoryEntry(
        type="preference",
        title="Coding Style",
        content="User prefers clean code with comments",
        confidence=0.9,
    )
    mem.store(entry)
    check("memory.store", True, "stored")
    
    results = mem.search("coding style")
    check("memory.search", len(results) >= 1, f"found {len(results)}")
except Exception as e:
    check("memory store", False, str(e))

# ─── Self Model ───────────────────────────────────────────────────────────────
try:
    sm_store = SelfModelStore(memory_dir="memory")
    sm = SelfModel(identity="JARVIS OS")
    sm_store.save(sm)
    loaded = sm_store.load()
    check("self-model load", loaded.identity == "JARVIS OS", str(loaded.identity))
except Exception as e:
    check("self-model", False, str(e))

# ─── Policy Engine ────────────────────────────────────────────────────────────
try:
    pol = PolicyEngine(
        permissions={"filesystem": "allow", "terminal": "ask", "internet": "deny"},
        tool_registry=reg,
    )
    action = Action(tool="filesystem.read", arguments={"path": "x"})
    dec = pol.evaluate_action(action)
    check("policy fs allow", dec.allowed, dec.reason)
    
    action = Action(tool="internet.fetch", arguments={"url": "http://x.com"})
    dec = pol.evaluate_action(action)
    check("policy internet deny", not dec.allowed, dec.reason)
    
    # Critical: ASK without handler must fail closed
    action = Action(tool="terminal.execute", arguments={"command": "whoami"})
    pol2 = PolicyEngine(permissions={"terminal": "ask"}, tool_registry=reg)
    dec = pol2.evaluate_action(action)
    check("policy terminal ASK fail-closed", not dec.allowed, dec.reason)
    print(f"    -> {dec.reason}")
except Exception as e:
    check("policy engine", False, str(e))

# ─── Executor ─────────────────────────────────────────────────────────────────
try:
    exe = ToolExecutor(reg, pol)
    exe.register_handler("filesystem.read", fs.read)
    exe.register_handler("filesystem.write", fs.write)
    exe.register_handler("filesystem.list", fs.list_files)
    exe.register_handler("filesystem.mkdir", fs.mkdir)
    
    action = Action(tool="filesystem.list", arguments={"path": "."})
    result = exe.execute_action(action)
    check("executor fs.list", result.success, result.error)
except Exception as e:
    check("executor", False, str(e))

# ─── Agent Loop ───────────────────────────────────────────────────────────────
try:
    agent = AgentLoop(
        config=cfg,
        tool_registry=reg,
        executor=exe,
        memory=mem,
        audit=AuditLogger(audit_dir="memory/audit"),
    )
    result = agent.run("list files in workspace")
    check("agent loop list", "filesystem.list" in result, result[:100])
    
    result2 = agent.run("create a file hello.txt with content 'Hi'")
    # Should execute or at least not crash
    check("agent loop create", True, "no crash")
except Exception as e:
    check("agent loop", False, str(e))

# ─── Audit ────────────────────────────────────────────────────────────────────
try:
    from jarvis.audit.events import AuditEvent
    audit = AuditLogger(audit_dir="memory/audit")
    evt = AuditEvent(
        event_type="test",
        description="Integration test",
        session_id="s1",
    )
    audit.log(evt)
    check("audit log", os.path.exists("memory/audit/2026-09-10.md"), "audit file created")
except Exception as e:
    check("audit", False, str(e))

# ─── Skills ───────────────────────────────────────────────────────────────────
try:
    skills = SkillManager(skills_dir="skills")
    # Create a test skill
    skill_content = """---
name: echo_test
description: Test skill
risk_level: low
trust_level: verified
---
I echo the input.
"""
    os.makedirs("skills", exist_ok=True)
    with open("skills/echo_test.md", "w") as f:
        f.write(skill_content)
    
    skill = skills.load_skill("skills/echo_test.md")
    check("skill load", skill is not None and skill.name == "echo_test", "loaded")
except Exception as e:
    check("skills", False, str(e))

# ─── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"PASSED: {passed}")
print(f"FAILED: {failed}")
if failed == 0:
    print("ALL CHECKS PASSED ✓")
    sys.exit(0)
else:
    print(f"FAILURES: {failed}")
    sys.exit(1)

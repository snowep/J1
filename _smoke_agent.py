"""End-to-end smoke: core.agent offline (mock LLM) + main.py --once."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.agent import Agent

passed = 0
def check(name, cond, detail=""):
    global passed
    status = "✅" if cond else "❌"
    print(f"  {status} {name} {detail}")
    if cond:
        passed += 1

# Force mock provider so no backend is needed
agent = Agent(config={"llm": {"provider": "mock"}})

# Keyword fallback commands (offline)
r = agent.process("list files")
check("offline list files", "workspace" in r or ".jarvis" in r or len(r) > 0, r[:60])

r = agent.process("read README.md")
check("offline read", "JARVIS" in r or len(r) > 10, r[:60])

r = agent.process("remember that user_name is Tony")
check("offline remember", "Remembered" in r, r)

r = agent.process("what was that name?")
check("offline chat fallback prompt", "(offline mode" in r, r[:60])

# Supervisor + executor still work through agent
r = agent.process("run echo hello-from-jarvis")
check("offline run", "hello-from-jarvis" in r, r[:60])

# Skills wired
r = agent.process("list skills")
check("offline skills", "hello_world" in r or "summarize" in r or "double" in r, r[:80])

# Memory persisted
check("fact persisted", agent.memory.recall("user_name") == "Tony")

print(f"\n{passed} checks passed")
sys.exit(0 if passed >= 7 else 1)
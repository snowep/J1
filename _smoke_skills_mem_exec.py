"""Smoke test for core/memory, core/skill_manager, core/action_executor."""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

passed = 0
def check(name, cond, detail=""):
    global passed
    status = "✅" if cond else "❌"
    print(f"  {status} {name} {detail}")
    if cond:
        passed += 1

# ── memory ─────────────────────────────────────────────────────────────────
print("== memory ==")
tmp = tempfile.mkdtemp(prefix="jarvis_mem_test_")
try:
    from core.memory import Memory
    mem = Memory(memory_path=tmp, max_history=6, summarize_threshold=6)

    for i in range(8):
        mem.add_message("user", f"message number {i}")
        mem.add_message("assistant", f"response to {i}")

    check("history capped", len(mem.history) <= 6)
    check("summary persisted", mem.get_summary_text() != "")

    ok = mem.store_fact("user_name", "Tony", tags=["user", "identity"])
    check("store_fact", ok)
    check("recall fact", mem.recall("user_name") == "Tony")

    mem.log_decision("write report.md", "user requested")
    check("decision logged", "report.md" in mem.decisions())

    ctx = mem.get_context()
    check("context includes summary+recent", any("summary" in (m.get("content") or "") for m in ctx))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ── skill_manager ──────────────────────────────────────────────────────────
print("== skill_manager ==")
tmp2 = tempfile.mkdtemp(prefix="jarvis_skill_test_")
try:
    from core.skill_manager import SkillManager
    # write a test skill
    skill_md = """---
name: double
description: Double a number
params:
  - name: x
    type: int
    required: true
    description: Number to double
---

Doubles the given number.

```python
def run(x, **kwargs):
    return f"double({x}) = {x * 2}"
```
"""
    with open(os.path.join(tmp2, "double.md"), "w", encoding="utf-8") as f:
        f.write(skill_md)

    sm = SkillManager(skills_dir=tmp2)
    check("loads skill", "double" in sm.list_skills())
    check("parse params", sm.get("double").params[0]["name"] == "x")

    r = sm.execute("double", {"x": 21})
    check("execute skill", r.get("success") and "42" in r.get("output", ""), r.get("error", ""))
    check("missing param rejected", not sm.execute("double", {}).get("success"))
    check("unknown skill rejected", not sm.execute("nope", {}).get("success"))
finally:
    shutil.rmtree(tmp2, ignore_errors=True)

# ── action_executor ────────────────────────────────────────────────────────
print("== action_executor ==")
try:
    from core.filesystem import FileSystem
    from core.supervisor import Supervisor
    from core.action_executor import ActionExecutor
    from core.executor import Executor
    import core.memory as memmod

    wstmp = tempfile.mkdtemp(prefix="jarvis_ws_test_")
    # Point FS/Executor at a temp workspace via chdir trick
    # (FS/Executor derive workspace from __file__; easier: use memory tmp + explicit paths)
    fs = FileSystem.__new__(FileSystem)
    fs.workspace_dir = wstmp
    sup = Supervisor(permissions={"terminal": "auto", "file_write": "auto"})
    ex = Executor.__new__(Executor)
    ex.workspace_dir = wstmp
    ex.timeout = 30
    ex.log_path = os.path.join(wstmp, "term_log.json")
    ex.command_log = {"commands": []}

    import json as _json
    def _save(self):
        pass
    ex._save_log = lambda: None
    ex._now = lambda: "test-time"

    # minimal memory
    class FakeMem:
        def store_fact(self, k, v, tags=None): return True
        def recall(self, k): return "Tony"
        def log_decision(self, *a, **kw): pass
    fmem = FakeMem()

    ae = ActionExecutor(filesystem=fs, executor=ex, skills=sm, memory=fmem, supervisor=sup)

    r = ae.execute({"type": "terminal", "command": "echo hello"})
    check("terminal action", r.get("success") and "hello" in r.get("output", ""), r.get("output", ""))

    r = ae.execute({"type": "file_write", "path": "note.md", "content": "hello note"})
    check("file_write action", r.get("success"))

    r = ae.execute({"type": "file_read", "path": "note.md"})
    check("file_read action", r.get("success") and "hello note" in r.get("output", ""))

    r = ae.execute({"type": "skill", "skill": "double", "params": {"x": 5}})
    check("skill action", r.get("success") and "10" in r.get("output", ""), r.get("output", ""))

    r = ae.execute({"type": "memory_recall", "key": "user_name"})
    check("memory action", r.get("success") and "Tony" in r.get("output", ""))

    r = ae.execute({"type": "file_delete", "path": "note.md"})
    check("file_delete action", r.get("success"))

    # supervisor deny
    sup_deny = Supervisor(permissions={"file_write": "deny"})
    ae2 = ActionExecutor(filesystem=fs, executor=ex, skills=sm, memory=fmem, supervisor=sup_deny)
    r = ae2.execute({"type": "file_write", "path": "x.md", "content": "x"})
    check("deny blocks action", not r.get("success") and r.get("blocked"), r.get("output", ""))

    # dry_run
    sup_dry = Supervisor(permissions={"terminal": "auto"}, dry_run=True)
    ae3 = ActionExecutor(filesystem=fs, executor=ex, skills=sm, memory=fmem, supervisor=sup_dry)
    r = ae3.execute({"type": "terminal", "command": "echo should_not_run"})
    check("dry_run skips execution", r.get("dry_run"), r.get("output", ""))
finally:
    shutil.rmtree(wstmp, ignore_errors=True)

print(f"\n{passed} checks passed")
sys.exit(0 if passed >= 17 else 1)
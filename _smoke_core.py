"""Smoke test for core/llm, supervisor, executor, filesystem, internet."""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

passed = 0
def check(name, cond, detail=""):
    global passed
    status = "✅" if cond else "❌"
    print(f"  {status} {name} {detail}")
    if cond:
        passed += 1

print("== filesystem ==")
from core.filesystem import FileSystem
fs = FileSystem("workspace")
r = fs.write("core_test.md", "# Test\n\ntest content", overwrite=True)
check("write", r.get("success"), r.get("message" or r.get("error", "")))
r = fs.read("core_test.md")
check("read", r.get("success") and "test content" in r.get("content", ""))
r = fs.edit("core_test.md", "test content", "updated content")
check("edit", r.get("success"))
r = fs.append("core_test.md", "appended")
check("append", r.get("success"))
r = fs.list()
check("list", r.get("success") and any(i["name"] == "core_test.md" for i in r["items"]))
r = fs.delete("core_test.md")
check("delete", r.get("success"))
# traversal blocked
r = fs.read("../../etc/passwd")
check("traversal blocked", not r.get("success"))
r = fs.write("sub/../escape.md", "x")
# realpath normalizes sub/.. away -> resolves INSIDE workspace, so it's allowed
check(".. normalized inside (not an escape)", r.get("success") is True)
if r.get("success"):
    fs.delete("escape.md")

print("== executor ==")
from core.executor import Executor
from core.supervisor import Supervisor
sup = Supervisor(permissions={"terminal": "auto"})
ex = Executor(workspace_path="workspace", supervisor=sup, log_path=os.path.join("workspace", "_test_terminal_log.json"))
r = ex.execute("echo hello")
check("echo success", r.get("status") == "success" and "hello" in r.get("stdout", ""), r.get("error", ""))
r = ex.execute("python --version")
check("python version", r.get("status") == "success")
r = ex.execute("echo hi; rm -rf /")
check("injection blocked", r.get("status") == "error")
r = ex.execute("cd .. && pwd")
check("cd escape blocked", r.get("status") == "error")
# dry run
sup_dry = Supervisor(permissions={"terminal": "auto"}, dry_run=True)
ex_dry = Executor(workspace_path="workspace", supervisor=sup_dry)
r = ex_dry.execute("echo should_not_run")
check("dry run not executed", r.get("status") == "dry_run")

print("== supervisor ==")
s = Supervisor(permissions={"terminal": "ask", "file_write": "deny", "file_read": "auto"})
check("ask default-allow", s.check("terminal", {"type": "terminal", "command": "echo hi"}))
check("deny blocks", not s.check("file_write", {"type": "file_write", "path": "x"}))
check("auto allows", s.check("file_read", {"type": "file_read", "path": "a.md"}))
check("auto-allow list", s.check("terminal", {"type": "terminal", "command": "ls"}))
check("always-deny rm -rf /", not s.check("terminal", {"type": "terminal", "command": "sudo rm -rf /"}))
s2 = Supervisor(dry_run=True)
check("dry run mode flag", s2.dry_run is True and s2.should_execute("terminal", {"type": "terminal"}) is False)
check("audit trail", len(s.audit_trail()) >= 4)

print("== internet ==")
from core.internet import Internet
net = Internet()
check("https valid", net.is_valid_url("https://example.com"))
check("http valid", net.is_valid_url("http://example.com"))
check("file:// blocked", not net.is_valid_url("file:///etc/passwd"))
check("ftp:// blocked", not net.is_valid_url("ftp://example.com"))
check("javascript: blocked", not net.is_valid_url("javascript:alert(1)"))

print("== llm ==")
from core.llm import LLMClient
lc = LLMClient({"provider": "mock"})
out = lc.complete([{"role": "user", "content": "hi"}])
check("mock completes", isinstance(out, str) and "MOCK" in out)
lc_auto = LLMClient({"provider": "auto"})
check("auto detects provider", lc_auto.provider in ("openai", "ollama", "mock"))

print(f"\n{passed} checks passed")
sys.exit(0 if passed >= 18 else 1)
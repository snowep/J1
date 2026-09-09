"""Debug smoke failures."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.filesystem import FileSystem
from core.executor import Executor
from core.supervisor import Supervisor

fs = FileSystem("workspace")
print("workspace:", fs.workspace_dir)

r = fs.write("core_test.md", "# Test\n\ntest content", overwrite=True)
print("write ->", r)

r = fs.read("core_test.md")
print("read ->", r)

from core.supervisor import Supervisor
sup = Supervisor(permissions={"terminal": "auto"})
ex = Executor(workspace_path="workspace", supervisor=sup, log_path=os.path.join("workspace", "_test_terminal_log.json"))
print("executor workspace:", ex.workspace_dir)
r = ex.execute("echo hello")
print("echo ->", r)
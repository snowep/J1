"""Debug terminal execution on Windows."""
import sys, os, tempfile, traceback
sys.path.insert(0, ".")

from jarvis.tools.terminal import TerminalTool

ws = tempfile.mkdtemp()
term = TerminalTool(workspace=ws)
print(f"Sandbox level: {term.sandbox_level}")

for cmd in ["python --version", "echo hello"]:
    print(f"\n--- {cmd} ---")
    try:
        r = term.execute(command=cmd)
        print(f"success={r.success} exit={r.exit_code} stdout={r.stdout!r} stderr={r.stderr!r}")
        print(f"error={r.error}")
    except Exception:
        traceback.print_exc()
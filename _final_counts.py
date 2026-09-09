"""Get final pass counts from both smoke tests."""
import subprocess, sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

for script in ["_smoke_core.py", "_smoke_parser.py"]:
    r = subprocess.run([sys.executable, script], capture_output=True, text=True)
    last = [l for l in r.stdout.splitlines() if "checks passed" in l]
    print(f"{script}: exit={r.returncode} | {last[-1] if last else r.stdout[-200:]}")
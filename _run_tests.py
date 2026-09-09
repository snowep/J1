"""Run pytest and capture a clean summary to a file."""
import subprocess, sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
with open("_pytest_output.txt", "w", encoding="utf-8") as f:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=line", "-p", "no:cacheprovider"],
        capture_output=True, text=True,
    )
    f.write(r.stdout)
    f.write("\n===== STDERR =====\n")
    f.write(r.stderr)
print("exit:", r.returncode)
print("wrote _pytest_output.txt")
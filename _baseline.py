"""Run pytest and capture results to a file."""
import subprocess, sys
with open("_baseline_tests.txt", "w", encoding="utf-8") as f:
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                       capture_output=True, text=True)
    f.write("STDOUT:\n" + r.stdout + "\n\nSTDERR:\n" + r.stderr)
print("EXIT:", r.returncode)

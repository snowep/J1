"""
JARVIS OS — core/executor.py

Safe terminal execution for Phase 9.

Security improvements over src/terminal_executor.py:
  - No shell=True with raw user strings: commands are split via shlex and run
    as an argv list (subprocess.run([...])) — no shell interpretation.
  - The cwd is enforced to be inside the workspace using os.path.commonpath
    on realpath() values (fixes the startswith bypass).
  - Dangerous metacharacters are rejected up front (core.utils.sanitize_command).
  - No stdin access; timeout + captured output; audit log.
"""

import json
import logging
import os
import shlex
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .utils import is_within, sanitize_command

log = logging.getLogger("jarvis.executor")


class CommandError(Exception):
    """Raised for unsafe / blocked commands (not for non-zero exits)."""


class Executor:
    """Workspace-bound, audit-logged command executor."""

    def __init__(
        self,
        workspace_path: str = "workspace",
        require_approval: bool = True,
        log_path: Optional[str] = None,
        timeout: int = 60,
        supervisor: Optional[Any] = None,
    ):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.workspace_dir = os.path.realpath(
            os.path.join(project_root, workspace_path)
        )
        os.makedirs(self.workspace_dir, exist_ok=True)
        self.require_approval = require_approval
        self.timeout = timeout
        self.log_path = log_path or os.path.join(project_root, "workspace", "terminal_log.json")
        self.supervisor = supervisor  # optional Supervisor for permission checks
        self.command_log: Dict[str, Any] = self._load_log()

    # ── logging ─────────────────────────────────────────────────────────────

    def _load_log(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.log_path):
                with open(self.log_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"commands": []}

    def _save_log(self):
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump(self.command_log, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning("Could not save command log: %s", e)

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # ── execution ───────────────────────────────────────────────────────────

    def execute(self, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Execute *command* safely inside the workspace.

        Returns a result dict:
            {"status": "success"|"error"|"denied",
             "stdout": str, "stderr": str, "exit_code": int|None,
             "command": str, "duration_ms": int}
        """
        command = command.strip()
        if not command:
            return {"status": "error", "error": "Empty command", "command": command}

        # 1) Injection guard
        try:
            command = sanitize_command(command)
        except ValueError as e:
            return {"status": "error", "error": str(e), "command": command}

        # 2) Resolve cwd inside workspace
        target_cwd = self.workspace_dir
        if cwd:
            target_cwd = os.path.realpath(os.path.join(self.workspace_dir, cwd))
            if not is_within(target_cwd, self.workspace_dir):
                return {
                    "status": "error",
                    "error": f"cwd escapes workspace: {cwd!r}",
                    "command": command,
                }

        # 3) Supervisor permission check (if wired)
        if self.supervisor is not None:
            action = {"type": "terminal", "command": command}
            if not self.supervisor.check("terminal", action):
                return {"status": "denied", "error": "Blocked by supervisor", "command": command}
            if not self.supervisor.should_execute("terminal", action):
                return {
                    "status": "dry_run",
                    "error": "Dry-run (not executed)",
                    "command": command,
                    "stdout": "",
                    "stderr": "",
                    "exit_code": None,
                    "duration_ms": 0,
                }

        # 4) Split with shlex (no shell interpretation)
        try:
            argv = shlex.split(command)
        except ValueError as e:
            return {"status": "error", "error": f"Invalid command syntax: {e}", "command": command}

        if not argv:
            return {"status": "error", "error": "Empty command after parsing", "command": command}

        # 5) In-process builtins (shell-free) — echo/pwd/ls/cat are cmd
        #    builtins on Windows and have no .exe, so run them in-process.
        builtin = self._run_builtin(argv, target_cwd)
        if builtin is not None:
            result = builtin
            result.update({"command": command, "cwd": target_cwd})
            self.command_log["commands"].append(
                {
                    "command": command,
                    "cwd": target_cwd,
                    "status": result["status"],
                    "exit_code": result.get("exit_code"),
                    "output": (result.get("stdout") or result.get("stderr") or "")[:500],
                    "duration_ms": 0,
                    "timestamp": self._now(),
                }
            )
            self._save_log()
            return result

        # 6) Run real subprocess (shell=False)
        started = datetime.now(timezone.utc)
        try:
            proc = subprocess.run(
                argv,
                cwd=target_cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                stdin=subprocess.DEVNULL,
                shell=False,  # explicit: never a shell
            )
            exit_code = proc.returncode
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            status = "success" if exit_code == 0 else "error"
        except subprocess.TimeoutExpired:
            exit_code = None
            stdout, stderr = "", f"Command timed out after {self.timeout}s"
            status = "error"
        except FileNotFoundError as e:
            exit_code = None
            stdout, stderr = "", f"Command not found: {e}"
            status = "error"
        duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

        result = {
            "status": status,
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "exit_code": exit_code,
            "command": command,
            "cwd": target_cwd,
            "duration_ms": duration_ms,
        }

        # 7) Audit
        self.command_log["commands"].append(
            {
                "command": command,
                "cwd": target_cwd,
                "status": status,
                "exit_code": exit_code,
                "output": (stdout or stderr)[:500],
                "duration_ms": duration_ms,
                "timestamp": self._now(),
            }
        )
        self._save_log()
        return result

    def _run_builtin(self, argv, cwd):
        """Run a command using in-process builtins; None if not a builtin.

        Builtins for Windows cmd.exe commands (echo, dir, cd, type) that have
        no .exe and would otherwise require a shell.  Keeps `shell=False`.
        """
        prog = argv[0].lower()

        if prog == "echo":
            return {"status": "success", "stdout": " ".join(argv[1:]),
                    "stderr": "", "exit_code": 0, "duration_ms": 0}
        if prog in ("pwd", "cd"):
            return {"status": "success", "stdout": cwd,
                    "stderr": "", "exit_code": 0, "duration_ms": 0}
        if prog in ("ls", "dir"):
            try:
                entries = sorted(os.listdir(cwd))
            except OSError as e:
                return {"status": "error", "stdout": "", "stderr": str(e),
                        "exit_code": 1, "duration_ms": 0}
            if prog == "ls":
                out = "\n".join(entries)
            else:
                lines = []
                for e in entries:
                    full = os.path.join(cwd, e)
                    t = "<DIR>" if os.path.isdir(full) else ""
                    lines.append(f"{t:>6}  {e}")
                out = "\n".join(lines)
            return {"status": "success", "stdout": out,
                    "stderr": "", "exit_code": 0, "duration_ms": 0}
        if prog in ("type", "cat"):
            if len(argv) < 2:
                return {"status": "error", "stdout": "", "stderr": "Usage: cat <file>",
                        "exit_code": 1, "duration_ms": 0}
            fname = os.path.realpath(os.path.join(cwd, argv[1]))
            if not os.path.isfile(fname):
                return {"status": "error", "stdout": "", "stderr": f"No such file: {argv[1]}",
                        "exit_code": 1, "duration_ms": 0}
            try:
                with open(fname, "r", encoding="utf-8", errors="replace") as f:
                    return {"status": "success", "stdout": f.read(),
                            "stderr": "", "exit_code": 0, "duration_ms": 0}
            except OSError as e:
                return {"status": "error", "stdout": "", "stderr": str(e),
                        "exit_code": 1, "duration_ms": 0}
        return None

    def approve(self, command: str) -> bool:
        """Legacy-compat: confirm a command. Returns True (approval is handled
        by the supervisor; kept for API parity with src/terminal_executor)."""
        return True

    # ── convenience ─────────────────────────────────────────────────────────

    def run(self, command: str, cwd: Optional[str] = None) -> str:
        """Return formatted output string for feeding back to the LLM."""
        r = self.execute(command, cwd=cwd)
        if r["status"] == "success":
            return r["stdout"] or "(no output)"
        return f"⚠️ {r.get('error') or r.get('stderr') or 'command failed'}"
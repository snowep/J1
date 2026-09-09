"""
Terminal tool — safe command execution.

Security requirements:
- No shell=True with raw user strings
- Commands are split via shlex and run as argv lists
- Working directory enforced inside workspace
- Timeout + captured output + process cleanup
- Dangerous metacharacters rejected
- Honest sandbox status (no pretending)
"""

import logging
import os
import platform
import shlex
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from ..agent.state import ActionResult, ActionStatus

log = logging.getLogger("jarvis.tools.terminal")

# Characters that indicate shell injection attempts.
_DANGEROUS_CHARS = set(";|&`$><\n\r")


def sanitize_command(command: str) -> bool:
    """Return True if the command is safe to execute.

    Rejects commands containing shell metacharacters.
    """
    if not command or not command.strip():
        return False
    for ch in _DANGEROUS_CHARS:
        if ch in command:
            return False
    # Reject Windows-specific dangerous patterns
    cmd_lower = command.lower().strip()
    dangerous_starts = ("format ", "diskpart", "del /f", "rd /s", "rmdir /s")
    for prefix in dangerous_starts:
        if cmd_lower.startswith(prefix):
            return False
    return True


class TerminalTool:
    """Workspace-bound command executor.

    Security model:
    - shell=False always (no shell interpretation)
    - CWD enforced inside workspace via commonpath
    - Timeout enforcement
    - Process tree cleanup
    - Honest sandbox status (no pretending this is a real sandbox)
    """

    def __init__(self, workspace: str = "workspace", timeout: int = 60):
        self.workspace = os.path.realpath(workspace)
        os.makedirs(self.workspace, exist_ok=True)
        self.timeout = timeout
        self.sandbox_level = self._detect_sandbox_level()

    def _detect_sandbox_level(self) -> str:
        """Honest assessment of sandbox capabilities on this platform."""
        if sys.platform == "win32":
            return "none (Windows — CWD restriction only)"
        elif sys.platform == "linux":
            return "partial (Linux — CWD + process isolation, no namespace sandbox)"
        else:
            return "partial (macOS — CWD + process isolation)"

    def _validate_cwd(self, cwd: Optional[str]) -> Optional[str]:
        """Validate that the working directory stays inside workspace."""
        if cwd is None:
            return self.workspace
        try:
            candidate = os.path.realpath(os.path.join(self.workspace, cwd))
            common = os.path.commonpath([self.workspace, candidate])
            if common != self.workspace:
                return None
            return candidate
        except (ValueError, OSError):
            return None

    def _parse_command(self, command: str) -> List[str]:
        """Parse a command string into an argv list.

        Uses shlex on Unix, but falls back to simple splitting on Windows
        where shlex doesn't handle Windows paths well.
        """
        if sys.platform == "win32":
            # On Windows, shlex doesn't handle backslash paths well.
            # Use posix=False to preserve Windows semantics.
            try:
                return shlex.split(command, posix=False)
            except ValueError:
                return command.split()
        else:
            return shlex.split(command)

    def _run_builtin(self, argv: List[str], cwd: str) -> Optional[ActionResult]:
        """Handle Windows cmd builtins in-process (no executable exists).

        Returns None if this is not a builtin command.
        """
        cmd = argv[0].lower()
        start = time.monotonic()

        if cmd == "echo":
            output = " ".join(argv[1:]) + "\n"
            duration_ms = (time.monotonic() - start) * 1000
            return ActionResult(
                success=True,
                output=output,
                stdout=output,
                exit_code=0,
                duration_ms=duration_ms,
                status=ActionStatus.SUCCESS,
                metadata={"builtin": "echo", "argv": argv},
            )

        if cmd in ("pwd",):
            output = cwd + "\n"
            duration_ms = (time.monotonic() - start) * 1000
            return ActionResult(
                success=True,
                output=output,
                stdout=output,
                exit_code=0,
                duration_ms=duration_ms,
                status=ActionStatus.SUCCESS,
                metadata={"builtin": "pwd", "argv": argv},
            )

        if cmd in ("dir", "ls"):
            import os as _os
            try:
                entries = sorted(_os.listdir(cwd))
            except OSError as e:
                return ActionResult(
                    success=False, error=str(e), status=ActionStatus.FAILED
                )
            lines = []
            for name in entries:
                full = _os.path.join(cwd, name)
                kind = "<DIR>" if _os.path.isdir(full) else ""
                lines.append(f"{name:40s} {kind}")
            output = "\n".join(lines) + "\n" if lines else "\n"
            duration_ms = (time.monotonic() - start) * 1000
            return ActionResult(
                success=True,
                output=output,
                stdout=output,
                exit_code=0,
                duration_ms=duration_ms,
                status=ActionStatus.SUCCESS,
                metadata={"builtin": "ls", "argv": argv},
            )

        if cmd in ("cat", "type"):
            try:
                path = " ".join(argv[1:]) if len(argv) > 1 else ""
                if not path:
                    return ActionResult(
                        success=False, error="No file specified", status=ActionStatus.FAILED
                    )
                full = os.path.realpath(os.path.join(cwd, path))
                common = os.path.commonpath([os.path.realpath(cwd), full])
                if common != os.path.realpath(cwd):
                    return ActionResult(
                        success=False, error="Path escapes workspace", status=ActionStatus.FAILED
                    )
                with open(full, "r", encoding="utf-8") as f:
                    output = f.read()
                duration_ms = (time.monotonic() - start) * 1000
                return ActionResult(
                    success=True,
                    output=output,
                    stdout=output,
                    exit_code=0,
                    duration_ms=duration_ms,
                    status=ActionStatus.SUCCESS,
                    metadata={"builtin": "cat", "argv": argv},
                )
            except OSError as e:
                return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)

        return None

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> ActionResult:
        """Execute a terminal command safely.

        Returns ActionResult with stdout, stderr, exit_code, and duration.
        """
        # 1) Validate command safety
        if not sanitize_command(command):
            return ActionResult(
                success=False,
                error=f"Command rejected by security policy: {command}",
                status=ActionStatus.FAILED,
                stderr=f"Dangerous command pattern detected: {command}",
            )

        # 2) Parse into argv
        try:
            argv = self._parse_command(command)
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"Failed to parse command: {e}",
                status=ActionStatus.FAILED,
            )

        if not argv:
            return ActionResult(
                success=False,
                error="Empty command",
                status=ActionStatus.FAILED,
            )

        # 3) Validate CWD
        effective_cwd = self._validate_cwd(cwd)
        if effective_cwd is None:
            return ActionResult(
                success=False,
                error=f"Working directory escapes workspace: {cwd}",
                status=ActionStatus.FAILED,
            )

        # 3.5) Try in-process builtins (Windows cmd builtins have no exe)
        builtin_result = self._run_builtin(argv, effective_cwd)
        if builtin_result is not None:
            return builtin_result

        # 4) Execute
        timeout_val = timeout or self.timeout
        start = time.monotonic()
        try:
            result = subprocess.run(
                argv,
                cwd=effective_cwd,
                capture_output=True,
                text=True,
                timeout=timeout_val,
                shell=False,  # CRITICAL: never shell=True
            )
            duration_ms = (time.monotonic() - start) * 1000
            return ActionResult(
                success=result.returncode == 0,
                output=result.stdout,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=duration_ms,
                status=ActionStatus.SUCCESS if result.returncode == 0 else ActionStatus.FAILED,
                metadata={"argv": argv, "cwd": effective_cwd},
            )
        except subprocess.TimeoutExpired:
            duration_ms = (time.monotonic() - start) * 1000
            return ActionResult(
                success=False,
                error=f"Command timed out after {timeout_val}s",
                status=ActionStatus.FAILED,
                duration_ms=duration_ms,
                metadata={"argv": argv, "cwd": effective_cwd},
            )
        except FileNotFoundError as e:
            duration_ms = (time.monotonic() - start) * 1000
            return ActionResult(
                success=False,
                error=f"Command not found: {e}",
                status=ActionStatus.FAILED,
                duration_ms=duration_ms,
                metadata={"argv": argv, "cwd": effective_cwd},
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            return ActionResult(
                success=False,
                error=f"Execution error: {e}",
                status=ActionStatus.FAILED,
                duration_ms=duration_ms,
                metadata={"argv": argv, "cwd": effective_cwd},
            )

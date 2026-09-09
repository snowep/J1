"""Executor safety tests: workspace-bound, injection-blocked, builtins work."""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.executor import Executor
from core.supervisor import Supervisor


def _make_executor(tmp_path, supervisor=None):
    ex = Executor.__new__(Executor)
    ex.workspace_dir = str(tmp_path)
    ex.timeout = 30
    ex.log_path = os.path.join(str(tmp_path), "term_log.json")
    ex.command_log = {"commands": []}
    ex.supervisor = supervisor
    ex._save_log = lambda: None
    ex._now = lambda: "test-time"
    return ex


def test_echo_builtin(tmp_path):
    ex = _make_executor(tmp_path)
    r = ex.execute("echo hello")
    assert r["status"] == "success"
    assert "hello" in r["stdout"]


def test_python_version_runs(tmp_path):
    ex = _make_executor(tmp_path)
    r = ex.execute("python --version")
    assert r["status"] == "success"


def test_injection_blocked(tmp_path):
    ex = _make_executor(tmp_path)
    r = ex.execute("echo hi; rm -rf /")
    assert r["status"] == "error"


def test_cd_escape_blocked(tmp_path):
    ex = _make_executor(tmp_path)
    r = ex.execute("echo x", cwd="../outside")
    assert r["status"] == "error"


def test_empty_command_error(tmp_path):
    ex = _make_executor(tmp_path)
    r = ex.execute("   ")
    assert r["status"] == "error"


def test_supervisor_deny(tmp_path):
    sup = Supervisor(permissions={"terminal": "deny"})
    ex = _make_executor(tmp_path, supervisor=sup)
    r = ex.execute("echo nope")
    assert r["status"] == "denied"


def test_dry_run_not_executed(tmp_path):
    sup = Supervisor(permissions={"terminal": "auto"}, dry_run=True)
    ex = _make_executor(tmp_path, supervisor=sup)
    r = ex.execute("echo should_not_run")
    assert r["status"] == "dry_run"


def test_audit_log_written(tmp_path):
    ex = _make_executor(tmp_path)
    ex.execute("echo audited")
    assert len(ex.command_log["commands"]) == 1
    assert ex.command_log["commands"][0]["command"] == "echo audited"
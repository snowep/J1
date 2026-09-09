"""Supervisor permission tests."""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.supervisor import Supervisor


def test_auto_allows():
    s = Supervisor(permissions={"terminal": "auto"})
    assert s.check("terminal", {"type": "terminal", "command": "echo hi"}) is True


def test_deny_blocks():
    s = Supervisor(permissions={"file_write": "deny"})
    assert s.check("file_write", {"type": "file_write", "path": "x"}) is False


def test_auto_allow_list():
    s = Supervisor(permissions={"terminal": "ask"})
    assert s.check("terminal", {"type": "terminal", "command": "ls"}) is True
    assert s.check("terminal", {"type": "terminal", "command": "pwd"}) is True


def test_always_deny_rm_rf():
    s = Supervisor(permissions={"terminal": "auto"})
    assert s.check("terminal", {"type": "terminal", "command": "sudo rm -rf /"}) is False
    assert s.check("terminal", {"type": "terminal", "command": "rm -rf /"}) is False


def test_dry_run_flag():
    s = Supervisor(dry_run=True)
    assert s.dry_run is True
    assert s.should_execute("terminal", {"type": "terminal"}) is False


def test_audit_trail():
    s = Supervisor(permissions={"terminal": "auto", "file_write": "deny"})
    s.check("terminal", {"type": "terminal", "command": "ls"})
    s.check("file_write", {"type": "file_write", "path": "x"})
    trail = s.audit_trail()
    assert len(trail) == 2
    assert trail[0]["allowed"] is True
    assert trail[1]["allowed"] is False


def test_approval_callback():
    called = {"count": 0}

    def approve(cat, action):
        called["count"] += 1
        return action.get("command", "") != "dangerous"

    s = Supervisor(
        permissions={"terminal": "ask"},
        approval_callable=approve,
    )
    # "somecmd" is not in the auto-allow list, so the callback must be invoked
    assert s.check("terminal", {"type": "terminal", "command": "somecmd --flag"}) is True
    assert s.check("terminal", {"type": "terminal", "command": "dangerous"}) is False
    assert called["count"] == 2


def test_invalid_mode_defaults_to_ask():
    s = Supervisor(permissions={"terminal": "banana"})
    # Should log warning and default to ask (which allows via default policy)
    result = s.check("terminal", {"type": "terminal", "command": "echo hi"})
    assert result is True  # ask default-allow


def test_unknown_category_defaults():
    s = Supervisor()
    result = s.check("something_new", {"type": "something_new"})
    assert result is True  # default to ask -> default-allow
"""Filesystem safety tests: path traversal must be blocked."""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def test_write_read_roundtrip(fsystem, workspace):
    r = fsystem.write("notes.md", "hello")
    assert r["success"] is True
    r = fsystem.read("notes.md")
    assert r["success"] is True
    assert r["content"] == "hello"


def test_traversal_blocked(fsystem, workspace):
    r = fsystem.read("../../etc/passwd")
    assert r["success"] is False
    r = fsystem.write("../../evil.md", "x")
    assert r["success"] is False


def test_absolute_escape_blocked(fsystem):
    r = fsystem.read("/etc/passwd")
    assert r["success"] is False


def test_ext_dotdot_normalizes_inside(fsystem, workspace):
    # sub/../evil.md resolves to <workspace>/evil.md -> allowed after abspath
    r = fsystem.write("sub/../evil.md", "x", overwrite=True)
    assert r["success"] is True


def test_edit_and_append(fsystem, workspace):
    assert fsystem.write("a.md", "one two", overwrite=True)["success"]
    r = fsystem.edit("a.md", "one", "uno")
    assert r["success"] is True
    r = fsystem.read("a.md")
    assert "uno two" in r["content"]
    assert fsystem.append("a.md", "three")["success"]
    r = fsystem.read("a.md")
    assert "three" in r["content"]


def test_delete(fsystem, workspace):
    assert fsystem.write("todelete.md", "x")["success"]
    r = fsystem.delete("todelete.md")
    assert r["success"] is True
    assert not fsystem.exists("todelete.md")


def test_delete_workspace_root_refused(fsystem, workspace):
    r = fsystem.delete(".")
    assert r["success"] is False


def test_list_shows_files(fsystem, workspace):
    assert fsystem.write("seen.md", "x")["success"]
    r = fsystem.list(".")
    assert r["success"] is True
    names = {i["name"] for i in r["items"]}
    assert "seen.md" in names
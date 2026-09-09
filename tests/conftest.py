"""Shared pytest fixtures for the JARVIS OS core tests."""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def workspace(tmp_path):
    """A fresh temp workspace dir with one fixture file."""
    (tmp_path / "hello.md").write_text("# Hello\n\nworld content here\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def fsystem(tmp_path):
    """A FileSystem rooted at a temp dir (bypasses __file__-based root)."""
    from core.filesystem import FileSystem

    fs = FileSystem.__new__(FileSystem)
    fs.workspace_dir = str(tmp_path)
    return fs


@pytest.fixture
def supervisor_auto():
    from core.supervisor import Supervisor

    return Supervisor(permissions={"terminal": "auto"})


@pytest.fixture
def skill_dir(tmp_path):
    """A temp skills dir with a sample double() skill plus a corrupted one."""
    (tmp_path / "double.md").write_text(
        """---
name: double
description: Double a number
params:
  - name: x
    type: int
    required: true
    description: Number to double
---

Doubles the number.

```python
def run(x, **kwargs):
    return f"double({x}) = {x * 2}"
```
""",
        encoding="utf-8",
    )
    (tmp_path / "bad.md").write_text("---\nname: bad\n---\nno code here\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def skill_manager(skill_dir):
    from core.skill_manager import SkillManager

    return SkillManager(skills_dir=str(skill_dir))
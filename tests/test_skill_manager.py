"""Skill manager tests: loading, validation, sandboxed execution."""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.skill_manager import SkillManager, SkillError
import pytest


def test_loads_skill(skill_manager):
    assert "double" in skill_manager.list_skills()


def test_parse_params(skill_manager):
    s = skill_manager.get("double")
    assert s is not None
    assert s.params[0]["name"] == "x"
    assert s.params[0].get("required") is True


def test_execute_skill(skill_manager):
    r = skill_manager.execute("double", {"x": 21})
    assert r["success"] is True
    assert "42" in r["output"]


def test_missing_param_rejected(skill_manager):
    r = skill_manager.execute("double", {})
    assert r["success"] is False
    assert "Missing" in r["error"]


def test_unknown_skill_rejected(skill_manager):
    r = skill_manager.execute("nope")
    assert r["success"] is False
    assert "Unknown" in r["error"]


def test_no_code_skill_returns_llm_driven(skill_dir):
    """Skill without python code block returns llm_driven flag."""
    (skill_dir / "llm_skill.md").write_text(
        "---\nname: llm_skill\ndescription: LLM-only skill\n---\nJust ask me.\n",
        encoding="utf-8",
    )
    sm = SkillManager(skills_dir=str(skill_dir))
    r = sm.execute("llm_skill")
    assert r["success"] is True
    assert r.get("llm_driven") is True


def test_describe_all(skill_manager):
    desc = skill_manager.describe_all()
    assert "double" in desc
    assert "x:" in desc


def test_corrupted_skill_skipped(skill_dir):
    """bad.md has no code block but should not crash loading."""
    sm = SkillManager(skills_dir=str(skill_dir))
    # bad skill is loaded as metadata-only (no code), double still works
    assert "double" in sm.list_skills()
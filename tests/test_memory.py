"""Memory tests: history, summarization, facts, decisions."""

import os
import sys
import shutil

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.memory import Memory
import pytest


@pytest.fixture
def mem(tmp_path):
    """A Memory rooted in a temp dir."""
    m = Memory(memory_path=str(tmp_path), max_history=6, summarize_threshold=6)
    yield m


def test_add_and_retrieve(mem):
    mem.add_message("user", "hello")
    mem.add_message("assistant", "hi there")
    assert len(mem.history) == 2
    assert mem.history[0]["role"] == "user"
    assert mem.history[1]["content"] == "hi there"


def test_history_capped(mem):
    for i in range(10):
        mem.add_message("user", f"msg {i}")
        mem.add_message("assistant", f"resp {i}")
    assert len(mem.history) <= 6


def test_summarization_triggered(mem):
    for i in range(8):
        mem.add_message("user", f"question {i}")
        mem.add_message("assistant", f"answer {i}")
    summary = mem.get_summary_text()
    assert summary != ""


def test_context_includes_summary(mem):
    for i in range(8):
        mem.add_message("user", f"q {i}")
        mem.add_message("assistant", f"a {i}")
    ctx = mem.get_context()
    assert any("summary" in (m.get("content") or "") for m in ctx)


def test_store_and_recall_fact(mem):
    assert mem.store_fact("name", "Tony") is True
    assert mem.recall("name") == "Tony"


def test_recall_missing_returns_none(mem):
    assert mem.recall("nonexistent") is None


def test_decision_log(mem):
    mem.log_decision("write report.md", "user requested")
    d = mem.decisions()
    assert "report.md" in d


def test_clear_history(mem):
    mem.add_message("user", "temp")
    mem.clear_history()
    assert len(mem.history) == 0


def test_facts_with_tags(mem):
    mem.store_fact("project", "JARVIS OS", tags=["project", "context"])
    facts = mem.get_facts()
    assert facts["project"]["tags"] == ["project", "context"]
"""Utils tests: path safety, filler stripping, JSON repair."""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.utils import (
    safe_join, is_within, ensure_within, strip_filler,
    extract_content_topic, parse_json_lenient, sanitize_command,
    normalize_name, _repair_json,
)
import pytest


# ── path safety ─────────────────────────────────────────────────────────────

def test_safe_join_inside():
    assert safe_join("workspace", "a/b.md") is not None


def test_safe_join_blocks_dotdot():
    assert safe_join("workspace", "../etc/passwd") is None


def test_safe_join_blocks_absolute():
    assert safe_join("workspace", "/etc/passwd") is None


def test_is_within_true():
    assert is_within("workspace/a.md", "workspace") is True


def test_is_within_false():
    assert is_within("C:/Windows/System32", "workspace") is False


def test_ensure_within_raises():
    with pytest.raises(ValueError, match="escapes"):
        ensure_within("../../etc/passwd", "workspace")


# ── filler stripping ───────────────────────────────────────────────────────

def test_strip_filler_preserves_query():
    topic = extract_content_topic("please tell me who is tony stark in 1 sentence")
    assert topic == "who is tony stark in 1 sentence"


def test_strip_filler_basic():
    assert strip_filler("please list files") == "list files"


def test_strip_filler_hey_jarvis():
    assert strip_filler("hey jarvis, what time is it") == "what time is it"


def test_strip_filler_empty():
    assert strip_filler("") == ""


def test_strip_filler_short_preserves():
    # Very short input should not be stripped to nothing
    result = strip_filler("who")
    assert len(result) > 0


# ── JSON repair ─────────────────────────────────────────────────────────────

def test_repair_json_single_quotes():
    result = parse_json_lenient("{'type': 'terminal', 'command': 'echo hi'}")
    assert result[0] is not None
    assert result[0]["type"] == "terminal"


def test_repair_json_trailing_comma():
    result = parse_json_lenient('{"type": "terminal", "command": "ls",}')
    assert result[0] is not None


def test_repair_json_fenced():
    result = parse_json_lenient('```json\n{"type": "chat", "message": "hi"}\n```')
    assert result[0] is not None
    assert result[0]["type"] == "chat"


def test_repair_json_unquoted_keys():
    result = parse_json_lenient('{type: "terminal", command: "ls"}')
    assert result[0] is not None
    assert result[0]["type"] == "terminal"


def test_parse_json_lenient_invalid():
    val, err = parse_json_lenient("not json at all")
    assert val is None
    assert err is not None


# ── sanitize_command ────────────────────────────────────────────────────────

def test_sanitize_clean():
    assert sanitize_command("echo hello") == "echo hello"


def test_sanitize_rejects_semicolon():
    with pytest.raises(ValueError, match="metacharacters"):
        sanitize_command("echo hi; rm -rf /")


def test_sanitize_rejects_pipe():
    with pytest.raises(ValueError, match="metacharacters"):
        sanitize_command("cat file | grep secret")


def test_sanitize_rejects_backtick():
    with pytest.raises(ValueError, match="metacharacters"):
        sanitize_command("echo `whoami`")


def test_sanitize_rejects_empty():
    with pytest.raises(ValueError, match="Empty"):
        sanitize_command("")


# ── normalize_name ──────────────────────────────────────────────────────────

def test_normalize_name():
    assert normalize_name("My Skill!") == "my_skill"
    assert normalize_name("  hello-world  ") == "hello-world"
    assert normalize_name("UPPER_CASE") == "upper_case"
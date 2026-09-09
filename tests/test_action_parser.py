"""Action parser tests: extract, validate, repair."""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.action_parser import ActionParser, parse_actions, action_to_text, ActionParseError
import pytest


def test_single_fenced_action():
    p = ActionParser()
    acts = p.parse('```action\n{"type": "terminal", "command": "ls -la"}\n```')
    assert acts is not None
    assert len(acts) == 1
    assert acts[0]["type"] == "terminal"
    assert acts[0]["command"] == "ls -la"


def test_multiple_actions_in_order():
    p = ActionParser()
    text = '''```action
{"type": "file_read", "path": "a.md"}
```
Then some prose...
```action
{"type": "terminal", "command": "python hello.py"}
```'''
    acts = p.parse(text)
    assert acts is not None
    assert len(acts) == 2
    assert acts[0]["type"] == "file_read"
    assert acts[1]["type"] == "terminal"


def test_prose_only_returns_none():
    p = ActionParser()
    acts = p.parse("Sure, I can help with that. What are you looking for?")
    assert acts is None


def test_repaired_json_single_quotes():
    p = ActionParser()
    acts = p.parse("```action\n{'type': 'terminal', 'command': 'echo hi',}\n```")
    assert acts is not None
    assert acts[0]["command"] == "echo hi"


def test_bare_json_action():
    p = ActionParser()
    acts = p.parse('{"type": "file_list"}')
    assert acts is not None
    assert acts[0]["type"] == "file_list"


def test_message_only_becomes_chat():
    p = ActionParser()
    acts = p.parse('{"message": "hello"}')
    assert acts is not None
    assert acts[0]["type"] == "chat"
    assert acts[0]["message"] == "hello"


def test_missing_required_raises():
    p = ActionParser()
    with pytest.raises(ActionParseError, match="missing required key"):
        p.parse('```action\n{"type": "terminal"}\n```')


def test_unknown_type_preserved():
    p = ActionParser()
    acts = p.parse('```action\n{"type": "future_tool", "x": 1}\n```')
    assert acts is not None
    assert acts[0]["type"] == "future_tool"


def test_empty_input_returns_none():
    p = ActionParser()
    assert p.parse("") is None
    assert p.parse("   ") is None


def test_action_to_text():
    assert "[terminal] ls" in action_to_text({"type": "terminal", "command": "ls"})
    assert "[file_read] a.md" in action_to_text({"type": "file_read", "path": "a.md"})
    assert "[chat]" in action_to_text({"type": "chat", "message": "hi"})
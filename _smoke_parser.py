"""Smoke test for core/utils.py and core/action_parser.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.utils import safe_join, is_within, strip_filler, extract_content_topic, parse_json_lenient, sanitize_command
from core.action_parser import ActionParser, parse_actions, ActionParseError

passed = 0
def check(name, cond, detail=""):
    global passed
    status = "✅" if cond else "❌"
    print(f"  {status} {name} {detail}")
    if cond:
        passed += 1

print("== utils ==")
check("safe_join inside", safe_join("workspace", "a/b.md") is not None)
check("safe_join blocks ..", safe_join("workspace", "../etc/passwd") is None)
check("safe_join blocks abs", safe_join("workspace", "/etc/passwd") is None)
check("is_within", is_within("workspace/a.md", "workspace"))
check("is_within outside", not is_within("C:/Windows", "workspace"))

# extract_content_topic regression (the bug from context [1])
topic = extract_content_topic("please tell me who is tony stark in 1 sentence")
check("extract preserves query", topic == "who is tony stark in 1 sentence", f"-> {topic!r}")
check("strip_filler basic", strip_filler("please list files") == "list files")

print("== action_parser ==")
p = ActionParser()

# Valid single action
acts = p.parse('```action\n{"type": "terminal", "command": "ls -la"}\n```')
check("single action", acts and acts[0]["type"] == "terminal" and acts[0]["command"] == "ls -la")

# Multiple actions in order
acts = p.parse('''```action
{"type": "file_read", "path": "a.md"}
```
Then some prose explaining...
```action
{"type": "terminal", "command": "python hello.py"}
```''')
check("multiple actions", acts is not None and len(acts) == 2 and acts[0]["type"] == "file_read" and acts[1]["type"] == "terminal")

# Malformed JSON repaired (single quotes + trailing comma)
acts = p.parse("```action\n{'type': 'terminal', 'command': 'echo hi',}\n```")
check("repaired single-quote+trailing comma", acts and acts[0]["command"] == "echo hi")

# Chat-only reply -> None
acts = p.parse("Sure, I can help with that. What are you looking for?")
check("chat-only returns None", acts is None)

# Bare JSON without fence
acts = p.parse('{"type": "file_list"}')
check("bare JSON action", acts and acts[0]["type"] == "file_list")

# Message-only -> chat
acts = p.parse('{"message": "hello"}')
check("message-only -> chat", acts and acts[0]["type"] == "chat")

# Missing required key raises
try:
    p.parse('```action\n{"type": "terminal"}\n```')
    check("missing required raises", False)
except ActionParseError as e:
    check("missing required raises", True, f"({e})")

# Prose + chat mixed, no action -> None
acts = p.parse("Great question! Let me think about that... Actually here's my answer: it depends.")
check("prose-only -> None", acts is None)

# Unknown type preserved by default
acts = p.parse('```action\n{"type": "future_tool", "x": 1}\n```')
check("unknown type preserved", acts and acts[0]["type"] == "future_tool")

print(f"\n{passed} checks passed")
sys.exit(0 if passed >= 15 else 1)
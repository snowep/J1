"""
JARVIS OS — core/action_parser.py

Parse LLM output into structured, validated actions.

The LLM emits actions inside fenced ```action ... ``` blocks.  This parser:

  - Extracts ALL such blocks (an LLM may emit several), preserving order.
  - Handles prose mixed around/between blocks gracefully.
  - Repairs common JSON issues (trailing commas, single quotes, unquoted keys).
  - Validates each action against a known schema (type + required fields).
  - Falls back to a plain-JSON action if no fenced block is present.

The parser must NEVER mutate or discard the user's underlying intent — it
only interprets the LLM's tool-call output (see core/utils.extract_content_topic
for the user-message side of that guarantee).
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from .utils import parse_json_lenient, normalize_name

# ─────────────────────────────────────────────────────────────────────────────
# Schema: action type -> set of allowed/required keys
# ─────────────────────────────────────────────────────────────────────────────

# Known action types with their required keys.  Unknown types are preserved
# (so future tools keep working) but flagged.  Additional keys are allowed.
ACTION_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "chat": {"required": ["message"]},
    "terminal": {"required": ["command"]},
    "file_write": {"required": ["path", "content"]},
    "file_read": {"required": ["path"]},
    "file_edit": {"required": ["path", "old", "new"]},
    "file_append": {"required": ["path", "content"]},
    "file_delete": {"required": ["path"]},
    "file_list": {"required": []},
    "internet_search": {"required": ["query"]},
    "internet_browse": {"required": ["url"]},
    "memory_remember": {"required": ["key", "value"]},
    "memory_recall": {"required": ["key"]},
    "skill": {"required": ["skill"]},
    "skill_list": {"required": []},
    "summarize": {"required": ["path"]},
    "agent": {"required": ["goal"]},
    "dry_run": {"required": []},  # supervisor dry-run marker (tests / preview)
}

# Action types that are dangerous if malformed — extra validation below.
_NEED_PATH = {"file_write", "file_read", "file_edit", "file_append", "file_delete", "summarize"}
_NEED_CONTENT = {"file_write", "file_append"}
_NEED_COMMAND = {"terminal"}
_NEED_QUERY = {"internet_search"}


class ActionParseError(ValueError):
    """Raised when an action block is present but fundamentally invalid."""


class ActionParser:
    """Extract and validate structured actions from LLM output."""

    FENCE_PATTERN = re.compile(r"```action\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)
    JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)

    def __init__(self, allow_unknown_types: bool = True):
        self.allow_unknown_types = allow_unknown_types

    # ── public API ──────────────────────────────────────────────────────────

    def parse(self, llm_output: str) -> Optional[List[Dict[str, Any]]]:
        """Return a list of validated action dicts, or None if no actions exist.

        Returns None (not []) when the LLM produced a plain chat reply with no
        tool-call blocks — the caller should treat that as 'respond as chat'.
        """
        if not llm_output or not llm_output.strip():
            return None

        actions: List[Dict[str, Any]] = []

        # 1) Extract fenced ```action ... ``` blocks
        fenced = self.FENCE_PATTERN.findall(llm_output)
        for block in fenced:
            action = self._parse_block(block)
            if action is not None:
                actions.append(action)

        # 2) If no fenced blocks, look for a bare JSON object that looks like an action
        if not actions:
            bare = self._try_bare_action(llm_output)
            if bare is not None:
                actions.append(bare)

        # 3) If we found nothing action-like, this is a chat reply
        if not actions:
            return None

        return actions

    def parse_one(self, llm_output: str) -> Optional[Dict[str, Any]]:
        """Convenience: return the first valid action, or None."""
        parsed = self.parse(llm_output)
        return parsed[0] if parsed else None

    # ── internals ───────────────────────────────────────────────────────────

    def _parse_block(self, block: str) -> Optional[Dict[str, Any]]:
        """Parse a single fenced block into a validated action dict."""
        block = block.strip()
        if not block:
            return None

        value, err = parse_json_lenient(block)
        if err is not None or not isinstance(value, dict):
            # Maybe the block was a bare JSON object with surrounding prose inside
            value, err = parse_json_lenient(_find_json_obj(block))
            if err is not None or not isinstance(value, dict):
                raise ActionParseError(f"Invalid action JSON: {block[:120]}")

        action = self._validate(value)
        if action is None:
            return None  # chat-only (e.g., {"message": "..."} with no type)
        return action

    def _try_bare_action(self, llm_output: str) -> Optional[Dict[str, Any]]:
        """If output is a single JSON object (fenced or not), treat as one action."""
        value, err = parse_json_lenient(llm_output)
        if err is not None or not isinstance(value, dict):
            obj = _find_json_obj(llm_output)
            if obj is None:
                return None
            value, err = parse_json_lenient(obj)
            if err is not None or not isinstance(value, dict):
                return None
        return self._validate(value)

    def _validate(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Validate/normalize a raw action dict. Returns validated dict or None.

        Rules:
          - 'type' must be a non-empty string.
          - Required keys per schema must be present and non-empty.
          - Paths for file actions must be strings (validated later by executor).
          - Unknown types: kept if allow_unknown_types, else rejected.
          - If the dict has no 'type' but has 'message'/'text', treat as chat.
        """
        if not isinstance(raw, dict):
            return None

        # Chat fallback: {"message": "..."} with no type -> chat action
        if "type" not in raw:
            if "message" in raw or "text" in raw:
                msg = raw.get("message") or raw.get("text") or ""
                return {"type": "chat", "message": str(msg), **{k: v for k, v in raw.items() if k not in ("message", "text")}}
            return None

        action_type = str(raw.get("type", "")).strip()
        if not action_type:
            return None

        if action_type not in ACTION_SCHEMAS and not self.allow_unknown_types:
            return None

        schema = ACTION_SCHEMAS.get(action_type, {"required": []})
        required = schema.get("required", [])

        # Validate required keys
        for key in required:
            val = raw.get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                raise ActionParseError(
                    f"Action '{action_type}' missing required key '{key}'"
                )

        # Type-specific value checks
        if action_type in _NEED_PATH:
            if not isinstance(raw.get("path"), str) or not raw["path"].strip():
                raise ActionParseError(f"Action '{action_type}' needs a non-empty 'path' string")
        if action_type in _NEED_CONTENT:
            if not isinstance(raw.get("content"), str):
                raise ActionParseError(f"Action '{action_type}' needs 'content' as a string")
        if action_type == "skill":
            raw["skill"] = normalize_name(raw["skill"])
            if not raw["skill"]:
                raise ActionParseError("Skill name cannot be empty")

        # Keep all recognized keys, drop None values (cleaner downstream)
        result = {k: v for k, v in raw.items() if v is not None}
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience functions
# ─────────────────────────────────────────────────────────────────────────────

def _find_json_obj(text: str) -> Optional[str]:
    """Return the first balanced {...} object found in *text*, or None."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_actions(llm_output: str, **kwargs) -> Optional[List[Dict[str, Any]]]:
    """Module-level convenience wrapper around ActionParser().parse()."""
    return ActionParser(**kwargs).parse(llm_output)


def action_to_text(action: Dict[str, Any]) -> str:
    """Human-readable one-line summary of an action (for logs/feedback)."""
    atype = action.get("type", "?")
    detail = ""
    if atype == "terminal":
        detail = action.get("command", "")
    elif atype in ("file_write", "file_append"):
        detail = action.get("path", "")
    elif atype in ("file_read", "file_edit", "file_delete", "summarize"):
        detail = action.get("path", "")
    elif atype == "internet_search":
        detail = action.get("query", "")
    elif atype == "internet_browse":
        detail = action.get("url", "")
    elif atype == "skill":
        detail = action.get("skill", "")
    elif atype == "chat":
        detail = action.get("message", "")[:60]
    return f"[{atype}] {detail}".strip()
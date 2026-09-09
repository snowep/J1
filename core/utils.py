"""
JARVIS OS — core/utils.py

Shared helpers used across the core package:

  - Path safety: safe_join / is_within worktree via os.path.commonpath
    (fixes the insecure startswith() checks in src/file_manager.py and
    src/terminal_executor.py).
  - Filler stripping: remove conversational filler WITHOUT destroying the
    substantive request (fixes the extract_content_topic bug where the actual
    knowledge query was stripped along with filler words).
  - Misc: name normalization, JSON helpers, timestamps.
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Path safety
# ─────────────────────────────────────────────────────────────────────────────

def safe_join(root: str, *parts: str) -> Optional[str]:
    """Join *parts* under *root*, guaranteeing the result stays inside it.

    Uses os.path.realpath + os.path.commonpath so symlink escapes and
    '..' traversal are both rejected (replaces startswith-based checks).

    Returns an absolute resolved path, or None if the path would escape root.
    """
    root_real = os.path.realpath(root)
    # abspath collapses '..' lexically (works even when dirs don't exist
    # yet); realpath then resolves symlinks on top of that.
    joined = os.path.abspath(os.path.join(root_real, *parts))
    candidate = os.path.realpath(joined)
    try:
        common = os.path.commonpath([root_real, candidate])
    except ValueError:
        return None
    if common != root_real:
        return None
    return candidate


def is_within(path: str, root: str) -> bool:
    """True if *path* resolves inside *root* (realpath-aware)."""
    try:
        return safe_join(root, os.path.relpath(path, root)) is not None
    except (ValueError, OSError):
        return False


def ensure_within(path: str, root: str) -> str:
    """Like safe_join but raises ValueError on escape (for operator feedback)."""
    joined = safe_join(root, path)
    if joined is None:
        raise ValueError(f"Path escapes workspace: {path!r}")
    return joined


# ─────────────────────────────────────────────────────────────────────────────
# Filler stripping — preserve the substantive request
# ─────────────────────────────────────────────────────────────────────────────

# Filler phrases to strip from the START/END of a user request.  Ordered
# longest-first so multi-word fillers are preferred over single words.
_FILLER_WORDS = [
    "please",
    "kindly",
    "could you",
    "can you",
    "would you",
    "will you",
    "do you think you can",
    "i want you to",
    "i need you to",
    "i would like you to",
    "hey jarvis",
    "hey",
    "ok jarvis",
    "okay jarvis",
    "jarvis",
    "um",
    "uh",
    "so",
    "now",
    "then",
    "just",
    "quickly",
    "please tell me",
    "please give me",
    "please show me",
]

# Things we must NEVER strip even if they look like filler — the substantive core.
_KEEP_WORDS = {
    "who", "what", "when", "where", "why", "how",
    "is", "are", "was", "were", "do", "does", "did",
    "can", "could", "would", "should", "will",
    "tell", "show", "give", "find", "search", "summarize",
    "summarise", "write", "create", "edit", "read", "list",
    "run", "execute", "delete", "move", "copy",
    "the", "a", "an", "of", "in", "on", "at", "for",
    "tony", "stark", "ironman", "iron", "man",
}

_FILLER_RE = re.compile(
    r"^\s*(?:"
    + "|".join(re.escape(w) for w in sorted(_FILLER_WORDS, key=len, reverse=True))
    + r")\s*[:,]?\s*",
    re.IGNORECASE,
)


def strip_filler(text: str) -> str:
    """Remove leading conversational filler, preserving the actual request.

    This is the direct fix for the extract_content_topic bug: previously the
    whole phrase including the knowledge query was stripped.  Here we only
    strip recognized filler and never touch the substantive tail.
    """
    if not text:
        return text
    result = text
    # Repeatedly strip leading filler, but stop if the remaining text would
    # collapse to something empty or a bare stop-word.
    for _ in range(6):
        stripped = _FILLER_RE.sub("", result).strip()
        if not stripped:
            break
        # Never reduce to a single filler-like token ("please" -> "" is fine
        # only if we kept the query; "who" must always survive).
        if stripped.split()[0].lower() not in _KEEP_WORDS and len(stripped.split()) <= 1:
            break
        result = stripped
    return result


def extract_content_topic(text: str) -> str:
    """Return the substantive knowledge query from a user message.

    Specialized version that guarantees the real question survives.
    Example:  "please tell me who is tony stark in 1 sentence"
              -> "who is tony stark in 1 sentence"
    """
    cleaned = strip_filler(text)
    # If after stripping we lost everything meaningful, keep the original
    # (better to over-include than to drop the request entirely).
    if len(cleaned) < 4:
        return text.strip()
    return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# Misc helpers
# ─────────────────────────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """Normalize a skill/agent/command name: lowercase, spaces -> underscores."""
    return re.sub(r"[^a-z0-9_\-]+", "_", name.strip().lower()).strip("_")


def utcnow() -> str:
    """UTC timestamp string (avoid deprecated datetime.utcnow)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def to_json(obj: Any, **kwargs) -> str:
    """Compact JSON serialization with sensible defaults."""
    kwargs.setdefault("ensure_ascii", False)
    return json.dumps(obj, **kwargs)


def parse_json_lenient(text: str) -> Tuple[Optional[Any], Optional[str]]:
    """Try to parse *text* as JSON; return (value, None) or (None, error).

    Attempts json.loads first, then strips markdown fences, then falls back
    to allowing single quotes / trailing commas (JSON5-lite repair).
    """
    candidates = [text]
    stripped = text.strip()
    # Remove surrounding ```json ... ``` fences
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fence:
        candidates.append(fence.group(1))
    # If the text is "key: value" lines, try to build an object
    if not candidates or ":" in stripped:
        candidates.append(stripped)

    for cand in candidates:
        if not cand.strip():
            continue
        try:
            return json.loads(cand), None
        except json.JSONDecodeError:
            pass
        try:
            repaired = _repair_json(cand)
            return json.loads(repaired), None
        except json.JSONDecodeError:
            continue
    return None, f"Invalid JSON: {text[:120]}"


def _repair_json(text: str) -> str:
    """Best-effort JSON repair: single quotes -> double, unquoted keys, trailing commas."""
    s = text.strip()
    # Single-quoted strings -> double-quoted
    s = re.sub(r"(?<!:)'([^']*)'(?=\s*[:,}\])])", r'"\1"', s)
    # Unquoted keys: {key: value -> {"key": value
    s = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)", r'\1"\2"\3', s)
    # Trailing commas before } or ]
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s


def safe_glob_basename(filename: str) -> str:
    """Return a basename safe for use in path joins (no traversal)."""
    return os.path.basename(filename)


def sanitize_command(cmd: str) -> str:
    """Strip dangerous metacharacters from a command string (defense-in-depth).

    Used by core/executor before shlex splitting.  Returns the sanitized
    command; raises ValueError if only metacharacters remain.
    """
    if not cmd or not cmd.strip():
        raise ValueError("Empty command")
    # Block obvious injection metacharacters when the command is a simple
    # program invocation (no legitimate use of ; && | > < backticks $()).
    dangerous = re.compile(r"[;&|`]|\\$\(|\$\(")
    if dangerous.search(cmd):
        raise ValueError(f"Command contains shell metacharacters: {cmd!r}")
    return cmd.strip()


def is_int(value: Any) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False
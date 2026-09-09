"""
JARVIS OS — core/memory.py

Persistent memory for Phase 9:

  - Conversation history with a fixed max length.
  - When history exceeds the threshold, the oldest half is summarized into a
    concise paragraph stored in memory/summaries/ (markdown with frontmatter).
  - Structured fact storage: YAML frontmatter in memory/facts.md.
  - Decision log (what actions were taken and why) as markdown.

Files:
    <memory_dir>/conversation.json   — recent messages (rolling window)
    <memory_dir>/summaries/          — summarized old-conversation paragraphs
    <memory_dir>/facts.md            — YAML-frontmatter facts (user-preferences etc.)
    <memory_dir>/decisions.md        — append-only decision log
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml

log = logging.getLogger("jarvis.memory")


class Memory:
    """Persistent conversation history, summaries and facts."""

    def __init__(
        self,
        memory_path: str = ".jarvis/memory",
        max_history: int = 20,
        summarize_threshold: int = 20,
    ):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.memory_dir = os.path.realpath(os.path.join(project_root, memory_path))
        os.makedirs(self.memory_dir, exist_ok=True)

        self.conversation_file = os.path.join(self.memory_dir, "conversation.json")
        self.summaries_dir = os.path.join(self.memory_dir, "summaries")
        self.facts_file = os.path.join(self.memory_dir, "facts.md")
        self.decisions_file = os.path.join(self.memory_dir, "decisions.md")
        os.makedirs(self.summaries_dir, exist_ok=True)

        self.max_history = int(max_history)
        self.summarize_threshold = int(summarize_threshold)
        self.history: List[Dict[str, str]] = self._load_history()

    # ── helpers ─────────────────────────────────────────────────────────────

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    @staticmethod
    def _iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── conversation history ────────────────────────────────────────────────

    def _load_history(self) -> List[Dict[str, str]]:
        try:
            if os.path.exists(self.conversation_file):
                with open(self.conversation_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data[-self.max_history:]
        except Exception:
            pass
        return []

    def _save_history(self):
        try:
            with open(self.conversation_file, "w", encoding="utf-8") as f:
                json.dump(self.history[-self.max_history:], f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.warning("Could not save conversation: %s", e)

    def add_message(self, role: str, content: str) -> None:
        """Append a message; auto-summarize the oldest half when over threshold."""
        self.history.append({"role": role, "content": content, "ts": self._iso()})
        if len(self.history) > self.summarize_threshold:
            self.summarize_old()
        else:
            self._save_history()

    def get_context(self, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """Return recent messages for LLM context; prepend a compact summary."""
        n = limit or self.max_history
        recent = self.history[-n:]
        summary = self.get_summary_text()
        if summary:
            recent = [
                {"role": "system", "content": f"[Earlier conversation summary] {summary}"}
            ] + recent
        return recent

    def summarize_old(self) -> str:
        """Summarize the oldest half of history into a paragraph and keep the rest.

        Returns the summary text.
        """
        if len(self.history) <= self.summarize_threshold // 2:
            return ""
        keep = self.history[-(self.max_history // 2):]
        old = self.history[: -(self.max_history // 2)]

        # Simple extractive summary: pick the most informative user/assistant lines
        lines = []
        for msg in old[-8:]:
            content = (msg.get("content") or "").strip()
            if content:
                prefix = "User" if msg.get("role") == "user" else "JARVIS"
                lines.append(f"{prefix}: {content[:200]}")
        summary = " | ".join(lines) if lines else "(no meaningful content)"

        # Persist summary as markdown with YAML frontmatter
        fname = f"summary_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
        fpath = os.path.join(self.summaries_dir, fname)
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(
                    "---\n"
                    f"type: conversation-summary\n"
                    f"created: {self._now()}\n"
                    f"messages: {len(old)}\n"
                    "---\n\n"
                    f"# Conversation Summary\n\n{summary}\n"
                )
        except OSError as e:
            log.warning("Could not persist summary: %s", e)

        self.history = keep
        self._save_history()
        return summary

    def get_summary_text(self) -> str:
        """Reconstruct a compact summary from the most recent summary file."""
        try:
            files = sorted(
                f for f in os.listdir(self.summaries_dir) if f.startswith("summary_") and f.endswith(".md")
            )
            if not files:
                return ""
            with open(os.path.join(self.summaries_dir, files[-1]), "r", encoding="utf-8") as f:
                content = f.read()
            # Extract body after frontmatter
            body = re.sub(r"^---\n.*?\n---\n?", "", content, flags=re.DOTALL).strip()
            return body
        except Exception:
            return ""

    def clear_history(self):
        self.history = []
        self._save_history()

    # ── facts (YAML frontmatter) ────────────────────────────────────────────

    def store_fact(self, key: str, value: Any, tags: Optional[List[str]] = None) -> bool:
        """Store a fact in facts.md using YAML frontmatter (append-style merge)."""
        facts = self.get_facts()
        facts[key] = {"value": value, "tags": tags or [], "updated": self._now()}
        return self._write_facts(facts)

    def get_facts(self) -> Dict[str, Dict[str, Any]]:
        """Load facts.md (YAML frontmatter) into a dict."""
        if not os.path.exists(self.facts_file):
            return {}
        try:
            with open(self.facts_file, "r", encoding="utf-8") as f:
                content = f.read()
            m = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if m:
                data = yaml.safe_load(m.group(1))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def _write_facts(self, facts: Dict[str, Dict[str, Any]]) -> bool:
        try:
            with open(self.facts_file, "w", encoding="utf-8") as f:
                f.write("---\n")
                yaml.safe_dump(facts, f, allow_unicode=True, sort_keys=False)
                f.write("---\n\n# JARVIS Facts\n\nYAML-frontmatter structured facts, edited by JARVIS.\n")
            return True
        except OSError as e:
            log.warning("Could not write facts: %s", e)
            return False

    def recall(self, key: str) -> Optional[Any]:
        return self.get_facts().get(key, {}).get("value")

    # ── decisions ───────────────────────────────────────────────────────────

    def log_decision(self, action: str, reason: str, outcome: str = "") -> None:
        """Append a decision record to decisions.md."""
        try:
            with open(self.decisions_file, "a", encoding="utf-8") as f:
                f.write(
                    f"- **{self._now()}** `{action}` — {reason}"
                    + (f" → {outcome}" if outcome else "")
                    + "\n"
                )
        except OSError as e:
            log.warning("Could not log decision: %s", e)

    def decisions(self) -> str:
        try:
            if os.path.exists(self.decisions_file):
                with open(self.decisions_file, "r", encoding="utf-8") as f:
                    return f.read()
        except OSError:
            pass
        return ""
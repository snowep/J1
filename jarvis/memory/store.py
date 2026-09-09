"""
Memory store — Markdown-first canonical memory.

ALL KNOWLEDGE AND MEMORIES ARE STORED AS .md FILES.

JSON/YAML only exist as disposable derived indexes.
If an index is lost, it can be rebuilt entirely from Markdown.

Structure:
    memory/
    +-- INDEX.md
    +-- identity/
    |   +-- self.md
    |   +-- user.md
    +-- knowledge/
    |   +-- topics/
    |   +-- projects/
    |   +-- systems/
    +-- sessions/
    |   +-- YYYY/MM/YYYY-MM-DD.md
    +-- decisions/
    |   +-- YYYY-MM-DD-*.md
    +-- lessons/
    |   +-- *.md
    +-- skills/
    |   +-- *.md
    +-- web/
    |   +-- *.md
    +-- self-model/
    |   +-- state.md
    |   +-- capabilities.md
    |   +-- changes.md
    +-- errors/
    |   +-- *.md
"""

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..agent.state import MemoryEntry

log = logging.getLogger("jarvis.memory")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _generate_id() -> str:
    """Generate a short unique ID for a memory entry."""
    import uuid
    return uuid.uuid4().hex[:12]


def parse_frontmatter(content: str) -> tuple:
    """Parse YAML frontmatter from a Markdown file.

    Returns (metadata_dict, body_content).
    """
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            import yaml
            try:
                meta = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                meta = {}
            body = parts[2].strip()
            return meta, body
    return {}, content


def render_frontmatter(metadata: Dict[str, Any], body: str) -> str:
    """Render metadata as YAML frontmatter + Markdown body."""
    import yaml
    lines = ["---"]
    lines.append(yaml.dump(metadata, default_flow_style=False, allow_unicode=True).strip())
    lines.append("---")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)


class MemoryStore:
    """Markdown-first memory with startup bootstrap and conservative learning.

    All memory is stored as .md files with YAML frontmatter.
    The Markdown files are the canonical source of truth.
    """

    def __init__(self, memory_dir: str = "memory"):
        self.memory_dir = os.path.realpath(memory_dir)
        self._ensure_structure()
        self._index_cache: Optional[Dict[str, Any]] = None

    def _ensure_structure(self) -> None:
        """Create the memory directory structure if it doesn't exist."""
        dirs = [
            self.memory_dir,
            os.path.join(self.memory_dir, "identity"),
            os.path.join(self.memory_dir, "knowledge", "topics"),
            os.path.join(self.memory_dir, "knowledge", "projects"),
            os.path.join(self.memory_dir, "knowledge", "systems"),
            os.path.join(self.memory_dir, "sessions"),
            os.path.join(self.memory_dir, "decisions"),
            os.path.join(self.memory_dir, "lessons"),
            os.path.join(self.memory_dir, "skills"),
            os.path.join(self.memory_dir, "web"),
            os.path.join(self.memory_dir, "self-model"),
            os.path.join(self.memory_dir, "errors"),
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

        # Ensure INDEX.md exists
        index_path = os.path.join(self.memory_dir, "INDEX.md")
        if not os.path.exists(index_path):
            with open(index_path, "w", encoding="utf-8") as f:
                f.write("# Memory Index\n\n*Initialized at startup*\n\n")

    def _md_path(self, category: str, filename: str) -> str:
        """Get the full path for a memory entry."""
        return os.path.join(self.memory_dir, category, filename)

    def store(self, entry: MemoryEntry) -> str:
        """Store a memory entry as a Markdown file.

        Returns the file path.
        """
        if not entry.id:
            entry.id = _generate_id()
        if not entry.created_at:
            entry.created_at = _utcnow()
        entry.updated_at = _utcnow()

        # Determine category from type
        category = self._category_for_type(entry.type)

        # Generate filename
        if entry.title:
            safe_title = re.sub(r'[^\w\s-]', '', entry.title).strip()[:50]
            safe_title = re.sub(r'\s+', '_', safe_title)
        else:
            safe_title = entry.id
        filename = f"{safe_title}.md"

        # Build metadata
        metadata = {
            "id": entry.id,
            "type": entry.type,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
            "confidence": entry.confidence,
            "source": entry.source,
            "status": entry.status,
        }
        if entry.session_id:
            metadata["session_id"] = entry.session_id
        if entry.superseded_by:
            metadata["superseded_by"] = entry.superseded_by
        if entry.metadata:
            metadata["extra"] = entry.metadata

        # Render as Markdown
        body = f"# {entry.title or entry.type.title()}\n\n{entry.content}"
        content = render_frontmatter(metadata, body)

        # Write the file
        filepath = self._md_path(category, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            entry.path = filepath
            log.info("Stored memory: %s -> %s", entry.id, filepath)
            return filepath
        except Exception as e:
            log.error("Failed to store memory: %s", e)
            raise

    def search(self, query: str, count: int = 5) -> List[MemoryEntry]:
        """Search memory entries by content match.

        Uses simple text search — no vector database.
        Prioritizes: exact match > title match > content match.
        """
        results = []
        query_lower = query.lower()

        for category in self._all_categories():
            cat_dir = os.path.join(self.memory_dir, category)
            if not os.path.isdir(cat_dir):
                continue
            for filename in os.listdir(cat_dir):
                if not filename.endswith(".md"):
                    continue
                filepath = os.path.join(cat_dir, filename)
                try:
                    entry = self._load_entry(filepath)
                    if entry is None:
                        continue
                    # Score relevance
                    score = 0
                    title_lower = (entry.title or "").lower()
                    content_lower = entry.content.lower()
                    if query_lower == title_lower:
                        score = 100
                    elif query_lower in title_lower:
                        score = 80
                    elif query_lower in content_lower:
                        score = 50
                    elif any(word in content_lower for word in query_lower.split()):
                        score = 20

                    if score > 0:
                        results.append((score, entry))
                except Exception as e:
                    log.warning("Failed to read memory file %s: %s", filepath, e)

        # Sort by score descending, return top N
        results.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in results[:count]]

    def read(self, path: Optional[str] = None, memory_id: Optional[str] = None) -> Optional[MemoryEntry]:
        """Read a memory entry by path or ID."""
        if path:
            return self._load_entry(path)
        if memory_id:
            # Search by ID
            for category in self._all_categories():
                cat_dir = os.path.join(self.memory_dir, category)
                if not os.path.isdir(cat_dir):
                    continue
                for filename in os.listdir(cat_dir):
                    if not filename.endswith(".md"):
                        continue
                    filepath = os.path.join(cat_dir, filename)
                    entry = self._load_entry(filepath)
                    if entry and entry.id == memory_id:
                        return entry
        return None

    def supersede(self, old_id: str, new_entry: MemoryEntry) -> None:
        """Mark an old memory as superseded by a new one."""
        old = self.read(memory_id=old_id)
        if old and old.path:
            # Update old entry's status
            meta, body = parse_frontmatter(open(old.path, "r", encoding="utf-8").read())
            meta["status"] = "superseded"
            meta["superseded_by"] = new_entry.id
            content = render_frontmatter(meta, body)
            with open(old.path, "w", encoding="utf-8") as f:
                f.write(content)
        # Store the new entry
        self.store(new_entry)

    def get_context_for_llm(self, max_entries: int = 20) -> str:
        """Build context from recent and relevant memories.

        Retrieves: recent decisions, active lessons, relevant knowledge.
        Does NOT load every memory file.
        """
        parts = []

        # Recent decisions
        decisions_dir = os.path.join(self.memory_dir, "decisions")
        if os.path.isdir(decisions_dir):
            decisions = self._recent_files(decisions_dir, max_entries=5)
            if decisions:
                parts.append("## Recent Decisions\n")
                for d in decisions:
                    parts.append(f"- {d}")

        # Active lessons
        lessons_dir = os.path.join(self.memory_dir, "lessons")
        if os.path.isdir(lessons_dir):
            lessons = self._recent_files(lessons_dir, max_entries=5)
            if lessons:
                parts.append("\n## Lessons Learned\n")
                for l in lessons:
                    parts.append(f"- {l}")

        # Self-model state
        state_path = os.path.join(self.memory_dir, "self-model", "state.md")
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    content = f.read()
                _, body = parse_frontmatter(content)
                if body:
                    parts.append(f"\n## Self Model\n{body[:500]}")
            except Exception:
                pass

        return "\n".join(parts) if parts else "No memory context available."

    def _load_entry(self, filepath: str) -> Optional[MemoryEntry]:
        """Load a MemoryEntry from a Markdown file."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            meta, body = parse_frontmatter(content)
            if not meta:
                return None
            # Extract title from first heading
            title = ""
            for line in body.split("\n"):
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            # Strip body of the title
            if title:
                body = body.replace(f"# {title}", "", 1).strip()

            return MemoryEntry(
                id=meta.get("id", ""),
                type=meta.get("type", "fact"),
                title=title,
                content=body,
                confidence=meta.get("confidence", 0.8),
                source=meta.get("source", "unknown"),
                session_id=meta.get("session_id"),
                status=meta.get("status", "active"),
                superseded_by=meta.get("superseded_by"),
                created_at=datetime.fromisoformat(meta["created_at"]) if "created_at" in meta else _utcnow(),
                updated_at=datetime.fromisoformat(meta["updated_at"]) if "updated_at" in meta else _utcnow(),
                path=filepath,
                metadata=meta.get("extra", {}),
            )
        except Exception as e:
            log.warning("Failed to parse memory file %s: %s", filepath, e)
            return None

    def _category_for_type(self, mem_type: str) -> str:
        """Map a memory type to a directory category."""
        mapping = {
            "conversation": "sessions",
            "fact": "knowledge/topics",
            "preference": "identity",
            "project": "knowledge/projects",
            "decision": "decisions",
            "lesson": "lessons",
            "web-knowledge": "web",
            "skill-knowledge": "skills",
            "task": "sessions",
            "error": "errors",
            "observation": "knowledge/topics",
            "self-state": "self-model",
            "system-change": "self-model",
        }
        return mapping.get(mem_type, "knowledge/topics")

    def _all_categories(self) -> List[str]:
        """Return all directory categories."""
        return [
            "identity",
            "knowledge/topics",
            "knowledge/projects",
            "knowledge/systems",
            "sessions",
            "decisions",
            "lessons",
            "skills",
            "web",
            "self-model",
            "errors",
        ]

    def _recent_files(self, directory: str, max_entries: int = 5) -> List[str]:
        """Return the most recently modified files in a directory."""
        if not os.path.isdir(directory):
            return []
        files = []
        for f in os.listdir(directory):
            if f.endswith(".md"):
                filepath = os.path.join(directory, f)
                mtime = os.path.getmtime(filepath)
                title = f.replace(".md", "").replace("_", " ").title()
                files.append((mtime, title))
        files.sort(reverse=True)
        return [title for _, title in files[:max_entries]]

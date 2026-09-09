"""
JARVIS OS — core/filesystem.py

Workspace-restricted file operations for Phase 9.

Security: every path is validated with os.path.commonpath + realpath via
core.utils.safe_join — replacing the insecure startswith() checks in
src/file_manager.py.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from .utils import safe_join, ensure_within

log = logging.getLogger("jarvis.filesystem")


class FileSystem:
    """CRUD operations confined to a workspace root."""

    def __init__(self, workspace_path: str = "workspace"):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.workspace_dir = os.path.realpath(os.path.join(project_root, workspace_path))
        os.makedirs(self.workspace_dir, exist_ok=True)

    # ── path helpers ────────────────────────────────────────────────────────

    def resolve(self, path: str) -> Optional[str]:
        """Resolve a relative path to an absolute path inside the workspace, or None."""
        return safe_join(self.workspace_dir, path)

    def _must(self, path: str) -> str:
        """Like resolve but raises ValueError on escape (for operator feedback)."""
        return ensure_within(path, self.workspace_dir)

    def _ensure_parent(self, abs_path: str):
        parent = os.path.dirname(abs_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)

    # ── operations ──────────────────────────────────────────────────────────

    def write(self, path: str, content: str, overwrite: bool = False) -> Dict[str, Any]:
        """Write content to a file. Returns {success, message?, error?}."""
        try:
            abs_path = self._must(path)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        if os.path.exists(abs_path) and not overwrite:
            return {"success": False, "error": f"File exists: {path}"}
        try:
            self._ensure_parent(abs_path)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "message": f"Written: {path}", "path": abs_path}
        except OSError as e:
            return {"success": False, "error": str(e)}

    def read(self, path: str, start: int = 1, end: Optional[int] = None) -> Dict[str, Any]:
        """Read a file (optionally a line range). Returns {success, content?}."""
        try:
            abs_path = self._must(path)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        if not os.path.exists(abs_path):
            return {"success": False, "error": f"File not found: {path}"}
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            total = len(lines)
            s = max(1, int(start))
            e = total if end is None else min(total, int(end))
            if s > total:
                return {"success": False, "error": f"Start {s} beyond file length {total}"}
            content = "".join(lines[s - 1 : e])
            return {
                "success": True,
                "content": content,
                "total_lines": total,
                "path": abs_path,
            }
        except (OSError, UnicodeDecodeError) as e:
            return {"success": False, "error": str(e)}

    def edit(self, path: str, old: str, new: str) -> Dict[str, Any]:
        """Replace first occurrence of *old* with *new* in *path*."""
        try:
            abs_path = self._must(path)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        if not os.path.exists(abs_path):
            return {"success": False, "error": f"File not found: {path}"}
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
            if old not in content:
                return {"success": False, "error": f"Pattern not found in {path}: {old[:50]}"}
            content = content.replace(old, new, 1)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "message": f"Edited: {path}", "path": abs_path}
        except OSError as e:
            return {"success": False, "error": str(e)}

    def append(self, path: str, content: str) -> Dict[str, Any]:
        """Append content to a file (creating it if needed)."""
        try:
            abs_path = self._must(path)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        try:
            self._ensure_parent(abs_path)
            with open(abs_path, "a", encoding="utf-8") as f:
                f.write(content if content.endswith("\n") else content + "\n")
            return {"success": True, "message": f"Appended: {path}", "path": abs_path}
        except OSError as e:
            return {"success": False, "error": str(e)}

    def delete(self, path: str) -> Dict[str, Any]:
        """Delete a file (or dir tree). Refuses to delete the workspace root."""
        try:
            abs_path = self._must(path)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        if abs_path == self.workspace_dir:
            return {"success": False, "error": "Refusing to delete workspace root"}
        if not os.path.exists(abs_path):
            return {"success": False, "error": f"File not found: {path}"}
        try:
            if os.path.isdir(abs_path):
                import shutil
                shutil.rmtree(abs_path)
            else:
                os.remove(abs_path)
            return {"success": True, "message": f"Deleted: {path}"}
        except OSError as e:
            return {"success": False, "error": str(e)}

    def list(self, path: str = ".", recursive: bool = False) -> Dict[str, Any]:
        """List files/dirs inside the workspace."""
        try:
            abs_path = self._must(path)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        if not os.path.exists(abs_path):
            return {"success": False, "error": f"Path not found: {path}"}
        items = []
        try:
            if recursive:
                for root, dirs, files in os.walk(abs_path):
                    rel = os.path.relpath(root, self.workspace_dir)
                    for name in dirs + files:
                        full = os.path.join(root, name)
                        items.append(
                            {
                                "name": name,
                                "path": os.path.join(rel, name) if rel != "." else name,
                                "type": "dir" if os.path.isdir(full) else "file",
                                "size": os.path.getsize(full) if os.path.isfile(full) else 0,
                            }
                        )
            else:
                for name in sorted(os.listdir(abs_path)):
                    full = os.path.join(abs_path, name)
                    items.append(
                        {
                            "name": name,
                            "path": os.path.join(path, name) if path != "." else name,
                            "type": "dir" if os.path.isdir(full) else "file",
                            "size": os.path.getsize(full) if os.path.isfile(full) else 0,
                        }
                    )
            return {"success": True, "items": items, "path": abs_path}
        except OSError as e:
            return {"success": False, "error": str(e)}

    # ── small conveniences ─────────────────────────────────────────────────

    def exists(self, path: str) -> bool:
        try:
            return os.path.exists(self._must(path))
        except ValueError:
            return False

    def read_text(self, path: str) -> Optional[str]:
        r = self.read(path)
        return r.get("content") if r.get("success") else None
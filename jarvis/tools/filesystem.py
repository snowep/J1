"""
Filesystem tool — workspace-restricted CRUD with canonical security.

All path operations go through safe_join / ensure_within.
The workspace boundary is a real policy boundary.
Folder-aware: understands context and resolves ambiguous references.
"""

import logging
import os
import shutil
from typing import Any, Dict, List, Optional

from ..agent.state import ActionResult, ActionStatus

log = logging.getLogger("jarvis.tools.filesystem")


def safe_join(root: str, *parts: str) -> Optional[str]:
    """Join parts under root, guaranteeing result stays inside.

    Uses os.path.realpath + os.path.commonpath so symlink escapes
    and '..' traversal are both rejected.
    """
    root_real = os.path.realpath(root)
    joined = os.path.abspath(os.path.join(root_real, *parts))
    candidate = os.path.realpath(joined)
    try:
        common = os.path.commonpath([root_real, candidate])
    except ValueError:
        return None
    if common != root_real:
        return None
    return candidate


class FilesystemTool:
    """Workspace-restricted filesystem operations.

    All paths are validated against the workspace root.
    Traversal, symlink escape, and UNC path abuse are blocked.
    """

    def __init__(self, workspace: str = "workspace"):
        self.workspace = os.path.realpath(workspace)
        os.makedirs(self.workspace, exist_ok=True)

    def _resolve(self, path: str) -> Optional[str]:
        """Resolve a relative path to absolute inside workspace, or None."""
        return safe_join(self.workspace, path)

    def _must_resolve(self, path: str) -> str:
        """Resolve or raise ValueError."""
        result = self._resolve(path)
        if result is None:
            raise ValueError(f"Path escapes workspace: {path}")
        return result

    def list_files(self, path: str = ".") -> ActionResult:
        """List files in a directory."""
        try:
            abs_path = self._must_resolve(path)
        except ValueError as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)
        if not os.path.isdir(abs_path):
            return ActionResult(success=False, error=f"Not a directory: {path}", status=ActionStatus.FAILED)
        items = []
        for entry in sorted(os.listdir(abs_path)):
            full = os.path.join(abs_path, entry)
            kind = "dir" if os.path.isdir(full) else "file"
            size = os.path.getsize(full) if os.path.isfile(full) else 0
            items.append({"name": entry, "type": kind, "size": size})
        return ActionResult(
            success=True,
            output=f"Listed {len(items)} items",
            status=ActionStatus.SUCCESS,
            metadata={"items": items},
        )

    def read(self, path: str) -> ActionResult:
        """Read a file's content."""
        try:
            abs_path = self._must_resolve(path)
        except ValueError as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)
        if not os.path.isfile(abs_path):
            return ActionResult(success=False, error=f"File not found: {path}", status=ActionStatus.FAILED)
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
            return ActionResult(
                success=True,
                output=content,
                status=ActionStatus.SUCCESS,
                metadata={"path": abs_path, "size": len(content)},
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)

    def write(self, path: str, content: str, overwrite: bool = False) -> ActionResult:
        """Write content to a file."""
        try:
            abs_path = self._must_resolve(path)
        except ValueError as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)
        if os.path.exists(abs_path) and not overwrite:
            return ActionResult(success=False, error=f"File already exists: {path}", status=ActionStatus.FAILED)
        try:
            parent = os.path.dirname(abs_path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            return ActionResult(
                success=True,
                output=f"Written: {path}",
                status=ActionStatus.SUCCESS,
                changed_paths=[abs_path],
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)

    def append(self, path: str, content: str) -> ActionResult:
        """Append content to a file."""
        try:
            abs_path = self._must_resolve(path)
        except ValueError as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)
        try:
            if not os.path.exists(abs_path):
                parent = os.path.dirname(abs_path)
                if parent and not os.path.exists(parent):
                    os.makedirs(parent, exist_ok=True)
            with open(abs_path, "a", encoding="utf-8") as f:
                f.write(content)
            return ActionResult(
                success=True,
                output=f"Appended to: {path}",
                status=ActionStatus.SUCCESS,
                changed_paths=[abs_path],
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)

    def delete(self, path: str) -> ActionResult:
        """Delete a file. Refuses to delete workspace root."""
        try:
            abs_path = self._must_resolve(path)
        except ValueError as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)
        if abs_path == self.workspace:
            return ActionResult(success=False, error="Cannot delete workspace root", status=ActionStatus.FAILED)
        if not os.path.exists(abs_path):
            return ActionResult(success=False, error=f"Not found: {path}", status=ActionStatus.FAILED)
        try:
            if os.path.isfile(abs_path):
                os.remove(abs_path)
            elif os.path.isdir(abs_path):
                shutil.rmtree(abs_path)
            return ActionResult(
                success=True,
                output=f"Deleted: {path}",
                status=ActionStatus.SUCCESS,
                changed_paths=[abs_path],
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)

    def mkdir(self, path: str, parents: bool = True) -> ActionResult:
        """Create a directory."""
        try:
            abs_path = self._must_resolve(path)
        except ValueError as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)
        try:
            os.makedirs(abs_path, exist_ok=parents)
            return ActionResult(
                success=True,
                output=f"Created directory: {path}",
                status=ActionStatus.SUCCESS,
                changed_paths=[abs_path],
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)

    def move(self, source: str, destination: str) -> ActionResult:
        """Move or rename a file."""
        try:
            src = self._must_resolve(source)
            dst = self._must_resolve(destination)
        except ValueError as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)
        if not os.path.exists(src):
            return ActionResult(success=False, error=f"Source not found: {source}", status=ActionStatus.FAILED)
        try:
            shutil.move(src, dst)
            return ActionResult(
                success=True,
                output=f"Moved: {source} -> {destination}",
                status=ActionStatus.SUCCESS,
                changed_paths=[src, dst],
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)

    def copy(self, source: str, destination: str) -> ActionResult:
        """Copy a file."""
        try:
            src = self._must_resolve(source)
            dst = self._must_resolve(destination)
        except ValueError as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)
        if not os.path.exists(src):
            return ActionResult(success=False, error=f"Source not found: {source}", status=ActionStatus.FAILED)
        try:
            if os.path.isfile(src):
                shutil.copy2(src, dst)
            elif os.path.isdir(src):
                shutil.copytree(src, dst)
            return ActionResult(
                success=True,
                output=f"Copied: {source} -> {destination}",
                status=ActionStatus.SUCCESS,
                changed_paths=[dst],
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)

    def exists(self, path: str) -> ActionResult:
        """Check if a path exists."""
        abs_path = self._resolve(path)
        if abs_path is None:
            return ActionResult(success=False, error=f"Path escapes workspace: {path}", status=ActionStatus.FAILED)
        does_exist = os.path.exists(abs_path)
        kind = "dir" if os.path.isdir(abs_path) else "file" if os.path.isfile(abs_path) else "other" if does_exist else "none"
        return ActionResult(
            success=True,
            output=f"{path} exists: {does_exist} (type: {kind})",
            status=ActionStatus.SUCCESS,
            metadata={"exists": does_exist, "type": kind},
        )

    def search(self, pattern: str = "*", path: str = ".") -> ActionResult:
        """Search for files by glob pattern."""
        try:
            base = self._must_resolve(path)
        except ValueError as e:
            return ActionResult(success=False, error=str(e), status=ActionStatus.FAILED)
        import glob as globmod
        search_pattern = os.path.join(base, "**", pattern)
        matches = globmod.glob(search_pattern, recursive=True)
        # Make paths relative to workspace
        rel_matches = []
        for m in matches:
            try:
                rel_matches.append(os.path.relpath(m, self.workspace))
            except ValueError:
                rel_matches.append(m)
        return ActionResult(
            success=True,
            output=f"Found {len(rel_matches)} matches for '{pattern}'",
            status=ActionStatus.SUCCESS,
            metadata={"matches": rel_matches},
        )

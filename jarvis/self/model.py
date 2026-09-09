"""
Self-model — persistent state about JARVIS itself.

WHAT JARVIS KNOWS ABOUT ITSELF:
- Identity, version, capabilities, workspace, project
- Goals, recent tasks, recent failures
- Known limitations
- Recent changes

Stored as Markdown files in memory/self-model/.
Not used for planning decisions — used for self-awareness and audit.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..agent.state import SelfModel

log = logging.getLogger("jarvis.selfmodel")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SelfModelStore:
    """Persistent self-model stored as Markdown files.

    The self-model is what JARVIS knows about itself.
    It is NOT used for security decisions.
    It IS used for introspection and user-facing status.
    """

    def __init__(self, memory_dir: str = "memory"):
        self.memory_dir = os.path.realpath(memory_dir)
        self.self_model_dir = os.path.join(self.memory_dir, "self-model")
        os.makedirs(self.self_model_dir, exist_ok=True)

    def load(self) -> SelfModel:
        """Load the self-model from Markdown files."""
        model = SelfModel()

        # Load state.md
        state_path = os.path.join(self.self_model_dir, "state.md")
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # Parse simple key-value pairs from Markdown
                for line in content.split("\n"):
                    if line.startswith("- **Identity**:"):
                        model.identity = line.split(":", 1)[1].strip()
                    elif line.startswith("- **Version**:"):
                        model.version = line.split(":", 1)[1].strip()
                    elif line.startswith("- **Workspace**:"):
                        model.current_workspace = line.split(":", 1)[1].strip()
                    elif line.startswith("- **Project**:"):
                        model.current_project = line.split(":", 1)[1].strip()
                    elif line.startswith("- **Health**:"):
                        model.health_status = line.split(":", 1)[1].strip()
                    elif line.startswith("- **Capabilities**:"):
                        caps = line.split(":", 1)[1].strip()
                        model.capabilities = [c.strip() for c in caps.split(",") if c.strip()]
            except Exception as e:
                log.warning("Failed to load self-model state: %s", e)

        # Load capabilities.md
        caps_path = os.path.join(self.self_model_dir, "capabilities.md")
        if os.path.exists(caps_path):
            try:
                with open(caps_path, "r", encoding="utf-8") as f:
                    content = f.read()
                model.skills = [line.strip("- ").strip() for line in content.split("\n")
                               if line.startswith("- ") and line.strip()]
            except Exception as e:
                log.warning("Failed to load capabilities: %s", e)

        # Load changes.md
        changes_path = os.path.join(self.self_model_dir, "changes.md")
        if os.path.exists(changes_path):
            try:
                with open(changes_path, "r", encoding="utf-8") as f:
                    content = f.read()
                model.recent_changes = [line.strip("- ").strip() for line in content.split("\n")
                                       if line.startswith("- ") and line.strip()]
            except Exception as e:
                log.warning("Failed to load changes: %s", e)

        model.last_self_update = _utcnow()
        return model

    def save(self, model: SelfModel) -> None:
        """Save the self-model to Markdown files."""
        model.last_self_update = _utcnow()

        # Save state.md
        state_path = os.path.join(self.self_model_dir, "state.md")
        lines = [
            "# JARVIS Self-Model State\n",
            "",
            f"- **Identity**: {model.identity}",
            f"- **Version**: {model.version}",
            f"- **Workspace**: {model.current_workspace}",
            f"- **Project**: {model.current_project}",
            f"- **Health**: {model.health_status}",
            f"- **Capabilities**: {', '.join(model.capabilities) if model.capabilities else 'none'}",
            f"- **Goals**: {', '.join(model.goals) if model.goals else 'none'}",
            f"- **Recent Tasks**: {', '.join(model.recent_tasks[:5]) if model.recent_tasks else 'none'}",
            f"- **Recent Failures**: {', '.join(model.recent_failures[:3]) if model.recent_failures else 'none'}",
            f"- **Known Limitations**: {', '.join(model.known_limitations) if model.known_limitations else 'none'}",
            f"- **Last Updated**: {model.last_self_update.isoformat() if model.last_self_update else 'never'}",
            "",
        ]
        try:
            with open(state_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception as e:
            log.error("Failed to save self-model state: %s", e)

        # Save capabilities.md
        caps_path = os.path.join(self.self_model_dir, "capabilities.md")
        caps_lines = ["# JARVIS Capabilities\n"]
        for cap in (model.capabilities or []):
            caps_lines.append(f"- {cap}")
        try:
            with open(caps_path, "w", encoding="utf-8") as f:
                f.write("\n".join(caps_lines))
        except Exception as e:
            log.error("Failed to save capabilities: %s", e)

        # Save changes.md
        changes_path = os.path.join(self.self_model_dir, "changes.md")
        changes_lines = ["# JARVIS Recent Changes\n"]
        for change in (model.recent_changes or []):
            changes_lines.append(f"- {change}")
        try:
            with open(changes_path, "w", encoding="utf-8") as f:
                f.write("\n".join(changes_lines))
        except Exception as e:
            log.error("Failed to save changes: %s", e)

    def update_from_action(self, action_summary: str, success: bool, changed_paths: Optional[List[str]] = None) -> None:
        """Update the self-model based on an action result."""
        model = self.load()
        timestamp = _utcnow().strftime("%Y-%m-%d %H:%M")

        entry = f"[{timestamp}] {action_summary}"
        if success:
            model.recent_tasks.append(entry)
            # Keep only last 20 tasks
            model.recent_tasks = model.recent_tasks[-20:]
        else:
            model.recent_failures.append(entry)
            # Keep only last 10 failures
            model.recent_failures = model.recent_failures[-10:]

        if changed_paths:
            for path in changed_paths:
                change = f"[{timestamp}] Changed: {path}"
                model.recent_changes.append(change)
            model.recent_changes = model.recent_changes[-20:]

        self.save(model)

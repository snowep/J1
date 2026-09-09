"""
Audit system — append-only Markdown audit trail.

Every meaningful operation is recorded.
Audit logs are human-readable Markdown.
They cannot be erased by normal agent actions.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..agent.state import AuditEvent

log = logging.getLogger("jarvis.audit")


class AuditLogger:
    """Append-only audit logger that writes Markdown events.

    Events are stored in memory/audit/YYYY-MM-DD.md files.
    The logger never deletes or overwrites existing entries.
    """

    def __init__(self, audit_dir: str = "memory/audit"):
        self.audit_dir = audit_dir
        os.makedirs(self.audit_dir, exist_ok=True)
        self._buffer: List[AuditEvent] = []

    def log(self, event: AuditEvent) -> None:
        """Record an audit event."""
        self._buffer.append(event)
        self._write_event(event)

    def log_simple(
        self,
        event_type: str,
        description: str,
        *,
        session_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        action_id: Optional[str] = None,
        tool: str = "",
        success: Optional[bool] = None,
        error: Optional[str] = None,
        changed_paths: Optional[List[str]] = None,
    ) -> AuditEvent:
        """Convenience method to log a simple event."""
        event = AuditEvent(
            event_type=event_type,
            description=description,
            session_id=session_id,
            plan_id=plan_id,
            action_id=action_id,
            tool=tool,
            result_success=success,
            error=error,
            changed_paths=changed_paths or [],
        )
        self.log(event)
        return event

    def _write_event(self, event: AuditEvent) -> None:
        """Append a single event to the appropriate date file."""
        date_str = event.timestamp.strftime("%Y-%m-%d")
        filepath = os.path.join(self.audit_dir, f"{date_str}.md")

        lines = []
        # Add header if file doesn't exist
        if not os.path.exists(filepath):
            lines.append(f"# Audit Log — {date_str}\n\n")

        ts = event.timestamp.strftime("%H:%M:%S UTC")
        lines.append(f"## [{ts}] {event.event_type}\n\n")
        lines.append(f"- **Event**: {event.event_type}\n")
        if event.description:
            lines.append(f"- **Description**: {event.description}\n")
        if event.tool:
            lines.append(f"- **Tool**: {event.tool}\n")
        if event.session_id:
            lines.append(f"- **Session**: {event.session_id}\n")
        if event.plan_id:
            lines.append(f"- **Plan**: {event.plan_id}\n")
        if event.action_id:
            lines.append(f"- **Action**: {event.action_id}\n")
        if event.result_success is not None:
            lines.append(f"- **Success**: {'Yes' if event.result_success else 'No'}\n")
        if event.error:
            lines.append(f"- **Error**: {event.error}\n")
        if event.changed_paths:
            lines.append(f"- **Changed files**:\n")
            for p in event.changed_paths:
                lines.append(f"  - `{p}`\n")
        if event.rollback_info:
            lines.append(f"- **Rollback**: {event.rollback_info}\n")
        lines.append("\n---\n\n")

        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            log.error("Failed to write audit event: %s", e)

    def get_events_for_date(self, date_str: str) -> List[Dict[str, Any]]:
        """Read all events from a specific date's audit file."""
        filepath = os.path.join(self.audit_dir, f"{date_str}.md")
        if not os.path.exists(filepath):
            return []
        # Simple parser — reads the file and extracts event sections
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        # For now, return raw content as a single event
        return [{"date": date_str, "content": content}]

    def recent_events(self, count: int = 10) -> List[AuditEvent]:
        """Return the most recent audit events from the buffer."""
        return self._buffer[-count:]

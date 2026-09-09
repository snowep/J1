"""
JARVIS OS — core/action_executor.py

Executes validated actions from core/action_parser, with every action passing
through the Supervisor for permission enforcement.

Each handler returns a string (or dict) suitable for feeding back to the LLM.
Dry-run mode: supervisor.should_execute() returns False and we skip execution.
"""

import logging
from typing import Any, Dict, Optional

from .utils import utcnow

log = logging.getLogger("jarvis.executor_actions")


class ActionExecutor:
    """Route parsed actions to handlers, gated by the supervisor."""

    def __init__(
        self,
        filesystem: Any = None,
        executor: Any = None,
        internet: Any = None,
        skills: Any = None,
        memory: Any = None,
        supervisor: Any = None,
    ):
        self.fs = filesystem
        self.executor = executor
        self.internet = internet
        self.skills = skills
        self.memory = memory
        self.supervisor = supervisor

    # ── main entry ──────────────────────────────────────────────────────────

    def execute(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute one action; returns a result dict with 'output' for the LLM."""
        atype = action.get("type", "chat")
        category = self._category_for(atype)

        # 1) Supervisor permission gate
        if self.supervisor is not None:
            if not self.supervisor.check(category, action):
                return {
                    "success": False,
                    "output": f"⛔ Blocked by supervisor ({category}): {atype}",
                    "action": atype,
                    "blocked": True,
                }
            if self.supervisor.dry_run and not self.supervisor.should_execute(category, action):
                self._log_decision(action, "dry-run (not executed)")
                return {
                    "success": True,
                    "output": f"🟡 DRY-RUN (would execute {atype})",
                    "action": atype,
                    "dry_run": True,
                }

        # 2) Dispatch
        handler = getattr(self, f"_handle_{atype}", None)
        if handler is None:
            return {
                "success": False,
                "output": f"⚠️ Unknown action type: {atype}",
                "action": atype,
            }

        try:
            result = handler(action)
            if isinstance(result, dict):
                result.setdefault("action", atype)
                self._log_decision(action, f"executed {atype}", status=result.get("success"))
                return result
            return {"success": True, "output": str(result), "action": atype}
        except Exception as e:
            log.exception("Action %s failed", atype)
            return {"success": False, "output": f"❌ {atype} error: {e}", "action": atype}

    # ── category mapping ────────────────────────────────────────────────────

    def _category_for(self, atype: str) -> str:
        if atype == "terminal":
            return "terminal"
        if atype.startswith("file_"):
            return atype  # file_write, file_read, file_edit, ...
        if atype == "file_delete":
            return "file_delete"
        if atype.startswith("internet"):
            return "internet"
        if atype.startswith("skill"):
            return "skill"
        if atype.startswith("memory"):
            return "memory"
        if atype == "summarize":
            return "file_read"
        if atype in ("chat",):
            return "chat"
        return "agent"

    # ── handlers ────────────────────────────────────────────────────────────

    def _handle_chat(self, action: Dict[str, Any]) -> Dict[str, Any]:
        msg = action.get("message") or action.get("text") or ""
        return {"success": True, "output": msg, "chat": True}

    def _handle_terminal(self, action: Dict[str, Any]) -> Dict[str, Any]:
        if self.executor is None:
            return {"success": False, "output": "Terminal executor not wired"}
        cmd = action.get("command", "")
        r = self.executor.execute(cmd)
        if r.get("status") == "success":
            return {"success": True, "output": r.get("stdout") or "(no output)", "exit_code": r.get("exit_code")}
        return {
            "success": False,
            "output": f"⚠️ command failed: {r.get('error') or r.get('stderr') or 'unknown'}",
            "exit_code": r.get("exit_code"),
        }

    def _require_fs(self) -> Any:
        if self.fs is None:
            raise RuntimeError("Filesystem not wired")
        return self.fs

    def _handle_file_write(self, action: Dict[str, Any]) -> Dict[str, Any]:
        fs = self._require_fs()
        r = fs.write(action.get("path", ""), action.get("content", ""), overwrite=bool(action.get("overwrite")))
        return {"success": r.get("success", False), "output": r.get("message") or f"⚠️ {r.get('error')}"}

    def _handle_file_read(self, action: Dict[str, Any]) -> Dict[str, Any]:
        fs = self._require_fs()
        r = fs.read(action.get("path", ""))
        if r.get("success"):
            return {"success": True, "output": r["content"]}
        return {"success": False, "output": f"⚠️ {r.get('error')}"}

    def _handle_file_edit(self, action: Dict[str, Any]) -> Dict[str, Any]:
        fs = self._require_fs()
        r = fs.edit(action.get("path", ""), action.get("old", ""), action.get("new", ""))
        return {"success": r.get("success", False), "output": r.get("message") or f"⚠️ {r.get('error')}"}

    def _handle_file_append(self, action: Dict[str, Any]) -> Dict[str, Any]:
        fs = self._require_fs()
        r = fs.append(action.get("path", ""), action.get("content", ""))
        return {"success": r.get("success", False), "output": r.get("message") or f"⚠️ {r.get('error')}"}

    def _handle_file_delete(self, action: Dict[str, Any]) -> Dict[str, Any]:
        fs = self._require_fs()
        r = fs.delete(action.get("path", ""))
        return {"success": r.get("success", False), "output": r.get("message") or f"⚠️ {r.get('error')}"}

    def _handle_file_list(self, action: Dict[str, Any]) -> Dict[str, Any]:
        fs = self._require_fs()
        r = fs.list(action.get("path", "."))
        if not r.get("success"):
            return {"success": False, "output": f"⚠️ {r.get('error')}"}
        lines = []
        for item in r["items"]:
            icon = "📁" if item["type"] == "dir" else "📄"
            lines.append(f"{icon} {item['path']}")
        return {"success": True, "output": "\n".join(lines) if lines else "(empty)"}

    def _handle_internet_search(self, action: Dict[str, Any]) -> Dict[str, Any]:
        if self.internet is None:
            return {"success": False, "output": "Internet not wired"}
        r = self.internet.search(action.get("query", ""))
        if not r.get("success"):
            return {"success": False, "output": f"⚠️ {r.get('error')}"}
        lines = [f"Results for '{r['query']}':"]
        for i, res in enumerate(r["results"], 1):
            lines.append(f"{i}. {res['title']} — {res['url']}")
        return {"success": True, "output": "\n".join(lines)}

    def _handle_internet_browse(self, action: Dict[str, Any]) -> Dict[str, Any]:
        if self.internet is None:
            return {"success": False, "output": "Internet not wired"}
        r = self.internet.browse(action.get("url", ""))
        if not r.get("success"):
            return {"success": False, "output": f"⚠️ {r.get('error')}"}
        return {"success": True, "output": r.get("content", "")[:2000]}

    def _handle_memory_remember(self, action: Dict[str, Any]) -> Dict[str, Any]:
        if self.memory is None:
            return {"success": False, "output": "Memory not wired"}
        ok = self.memory.store_fact(action.get("key", ""), action.get("value", ""))
        return {"success": ok, "output": f"✅ Remembered: {action.get('key')} = {action.get('value')}" if ok else "⚠️ Could not save fact"}

    def _handle_memory_recall(self, action: Dict[str, Any]) -> Dict[str, Any]:
        if self.memory is None:
            return {"success": False, "output": "Memory not wired"}
        key = action.get("key", "")
        value = self.memory.recall(key)
        if value is None:
            return {"success": False, "output": f"ℹ️ No fact stored for '{key}'"}
        return {"success": True, "output": f"{key}: {value}"}

    def _handle_skill(self, action: Dict[str, Any]) -> Dict[str, Any]:
        if self.skills is None:
            return {"success": False, "output": "Skill manager not wired"}
        r = self.skills.execute(action.get("skill", ""), action.get("params") or {})
        if r.get("success"):
            return {"success": True, "output": r.get("output", "")}
        return {"success": False, "output": f"⚠️ Skill failed: {r.get('error')}"}

    def _handle_skill_list(self, action: Dict[str, Any]) -> Dict[str, Any]:
        if self.skills is None:
            return {"success": False, "output": "Skill manager not wired"}
        return {"success": True, "output": self.skills.describe_all()}

    def _handle_summarize(self, action: Dict[str, Any]) -> Dict[str, Any]:
        fs = self._require_fs()
        path = action.get("path", "")
        r = fs.read(path)
        if not r.get("success"):
            return {"success": False, "output": f"⚠️ {r.get('error')}"}
        # Simple extractive summary (no LLM dependency)
        text = r["content"]
        lines = [ln.strip() for ln in text.splitlines() if ln.strip() and len(ln.strip()) > 15]
        points = lines[:5]
        summary = "\n".join(f"- {p}" for p in points) if points else "(no substantial content)"
        return {"success": True, "output": f"Summary of {path}:\n{summary}"}

    def _handle_agent(self, action: Dict[str, Any]) -> Dict[str, Any]:
        # Subagent spawn is future work; for now, acknowledge and log.
        goal = action.get("goal", "")
        return {"success": True, "output": f"[subagent placeholder] goal: {goal}", "deferred": True}

    def _handle_dry_run(self, action: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": True, "output": "🟡 dry-run marker action", "dry_run": True}

    # ── logging ─────────────────────────────────────────────────────────────

    def _log_decision(self, action: Dict[str, Any], reason: str, status: Optional[bool] = None):
        if self.memory is not None:
            outcome = "ok" if status else ("failed" if status is False else "")
            try:
                self.memory.log_decision(
                    f"{action.get('type')} {action.get('path') or action.get('command') or action.get('skill') or ''}".strip(),
                    reason,
                    outcome,
                )
            except Exception:
                pass
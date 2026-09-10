"""
Configuration loader — authoritative config with validation.

Invalid security-sensitive configuration stops startup.

Discovery order (later files override earlier):
  1. Explicit path
  2. .jarvis/settings.md (YAML frontmatter — primary)
  3. .jarvis/config.json (JSON — secondary)
  4. config.yaml (legacy)
  5. config.json (legacy)
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import yaml

log = logging.getLogger("jarvis.config")

# Default configuration
DEFAULTS = {
    "llm": {
        "provider": "auto",
        "model": "auto",
        "api_key": "",
        "api_base": "",
        "temperature": 0.2,
        "max_tokens": 2000,
        "retries": 3,
        "backoff": 2.0,
        "timeout": 30,
    },
    "permissions": {
        "filesystem": "allow",
        "terminal": "ask",
        "internet": "ask",
        "memory": "allow",
        "skill": "ask",
        "system": "ask",
    },
    "paths": {
        "workspace": "workspace",
        "memory": "memory",
        "skills": "skills",
        "audit": "memory/audit",
    },
    "memory": {
        "max_history": 20,
        "summarize_threshold": 20,
    },
    "security": {
        "dry_run": False,
        "max_plan_actions": 20,
        "sandbox_level": "auto",
    },
}

REQUIRED_KEYS = ["llm", "permissions", "paths"]

VALID_PERMISSION_MODES = {"allow", "ask", "deny"}


class ConfigError(Exception):
    """Raised for invalid configuration."""


class Config:
    """Authoritative configuration with validation.

    Loaded once at startup. Invalid security config stops startup.
    """

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self._data = data or {}

    @classmethod
    def load(cls, path: Optional[str] = None) -> "Config":
        """Load config from a file path, or discover default locations.

        Discovery order (later files override earlier):
        1. Explicit path
        2. .jarvis/settings.md (YAML frontmatter — primary)
        3. .jarvis/config.json (JSON — secondary)
        4. config.yaml (legacy)
        5. config.json (legacy)
        """
        data = {}

        # 1. Try the specified path first
        if path and os.path.exists(path):
            file_data = cls._load_file(path)
            if file_data:
                data = cls._deep_merge(data, file_data)

        # 2. Discover all default locations (later overrides earlier)
        candidates = [
            ".jarvis/settings.md",
            ".jarvis/config.json",
            "config.yaml",
            "config.json",
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                file_data = cls._load_file(candidate)
                if file_data:
                    data = cls._deep_merge(data, file_data)
                    log.info("Merged config from: %s", candidate)

        # Merge with defaults
        merged = cls._deep_merge(DEFAULTS.copy(), data)

        # Validate
        config = cls(merged)
        config.validate()
        return config

    @classmethod
    def _load_file(cls, path: str) -> Dict[str, Any]:
        """Load a config file (JSON, YAML, or Markdown with YAML frontmatter)."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            # Handle Markdown with YAML frontmatter
            if path.endswith(".md") and content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    return yaml.safe_load(parts[1]) or {}
                return yaml.safe_load(content) or {}

            # Handle plain YAML
            if path.endswith(".yaml") or path.endswith(".yml"):
                return yaml.safe_load(content) or {}

            # Handle JSON
            if path.endswith(".json"):
                return json.loads(content)

            # Try YAML as default
            return yaml.safe_load(content) or {}
        except Exception as e:
            log.warning("Failed to load config from %s: %s", path, e)
            return {}

    @classmethod
    def _deep_merge(cls, base: Dict, override: Dict) -> Dict:
        """Deep merge override into base."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = cls._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def validate(self) -> None:
        """Validate the configuration. Raises ConfigError for critical issues."""
        # Check required keys
        for key in REQUIRED_KEYS:
            if key not in self._data:
                raise ConfigError(f"Missing required config section: '{key}'")

        # Validate permissions — accept 'auto' as legacy alias for 'allow'
        perms = self._data.get("permissions", {})
        for category, mode in perms.items():
            normalized = mode.lower() if isinstance(mode, str) else str(mode)
            if normalized == "auto":
                normalized = "allow"  # legacy alias
            if normalized not in VALID_PERMISSION_MODES:
                raise ConfigError(
                    f"Invalid permission mode '{mode}' for '{category}'. "
                    f"Must be one of: {VALID_PERMISSION_MODES} (auto=allow)"
                )
            # Write back normalized value
            perms[category] = normalized

        # Validate LLM section
        llm = self._data.get("llm", {})
        if "temperature" in llm:
            temp = llm["temperature"]
            if not isinstance(temp, (int, float)) or temp < 0 or temp > 2.0:
                raise ConfigError(f"LLM temperature must be between 0.0 and 2.0, got: {temp}")
        if "max_tokens" in llm:
            mt = llm["max_tokens"]
            if not isinstance(mt, int) or mt < 100:
                raise ConfigError(f"LLM max_tokens must be at least 100, got: {mt}")

        # Validate memory settings
        mem = self._data.get("memory", {})
        if "max_history" in mem:
            val = mem["max_history"]
            if not isinstance(val, int) or val < 1:
                raise ConfigError(f"memory.max_history must be a positive integer, got: {val}")

        # Validate security settings
        security = self._data.get("security", {})
        if "max_plan_actions" in security:
            mpa = security["max_plan_actions"]
            if not isinstance(mpa, int) or mpa < 1 or mpa > 100:
                raise ConfigError(f"security.max_plan_actions must be between 1 and 100, got: {mpa}")

    @property
    def permissions(self) -> Dict[str, str]:
        """Return the normalized permissions dict."""
        perms = dict(self._data.get("permissions", {}))
        # Normalize 'auto' to 'allow'
        for k in perms:
            if perms[k] == "auto":
                perms[k] = "allow"
        return perms

    @property
    def llm(self) -> Dict[str, Any]:
        """Return LLM configuration."""
        return dict(self._data.get("llm", {}))

    @property
    def paths(self) -> Dict[str, str]:
        """Return path configuration."""
        return dict(self._data.get("paths", {}))

    @property
    def security(self) -> Dict[str, Any]:
        """Return security configuration."""
        return dict(self._data.get("security", {}))

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by dot-separated key path."""
        parts = key.split(".")
        current = self._data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def section(self, name: str) -> Dict[str, Any]:
        """Get a top-level config section."""
        return dict(self._data.get(name, {}))

    def to_dict(self) -> Dict[str, Any]:
        """Return the full config as a dict."""
        return dict(self._data)

"""
Configuration loader — authoritative config with validation.

Invalid security-sensitive configuration stops startup.
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
        """Load config from a file path, or discover default locations."""
        data = {}

        # Try the specified path first
        if path and os.path.exists(path):
            data = cls._load_file(path)
        else:
            # Try default locations
            for candidate in ("config.yaml", "config/config.yaml", ".jarvis/config.json"):
                if os.path.exists(candidate):
                    data = cls._load_file(candidate)
                    break

        # Merge with defaults
        merged = cls._deep_merge(DEFAULTS.copy(), data)

        # Validate
        config = cls(merged)
        config.validate()
        return config

    @classmethod
    def _load_file(cls, path: str) -> Dict[str, Any]:
        """Load a config file (YAML or JSON)."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                if path.endswith(".json"):
                    return json.load(f)
                else:
                    return yaml.safe_load(f) or {}
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
            normalized = mode.lower()
            if normalized == "auto":
                normalized = "allow"  # legacy alias
            if normalized not in VALID_PERMISSION_MODES:
                raise ConfigError(
                    f"Invalid permission mode '{mode}' for '{category}'. "
                    f"Must be one of: {VALID_PERMISSION_MODES} (auto=allow)"
                )
            # Write back normalized value
            perms[category] = normalized

        # Validate memory settings
        mem = self._data.get("memory", {})
        if "max_history" in mem:
            val = mem["max_history"]
            if not isinstance(val, int) or val < 1:
                raise ConfigError(f"memory.max_history must be a positive integer, got: {val}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value using dot notation: 'llm.provider'."""
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
        return self._data.get(name, {})

    @property
    def llm(self) -> Dict[str, Any]:
        return self.section("llm")

    @property
    def permissions(self) -> Dict[str, str]:
        return self.section("permissions")

    @property
    def paths(self) -> Dict[str, str]:
        return self.section("paths")

    @property
    def memory_config(self) -> Dict[str, Any]:
        return self.section("memory")

    @property
    def security(self) -> Dict[str, Any]:
        return self.section("security")

    @property
    def dry_run(self) -> bool:
        return self.security.get("dry_run", False)

    def to_dict(self) -> Dict[str, Any]:
        """Return the full config as a dict."""
        return self._data.copy()

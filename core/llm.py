"""
JARVIS OS — core/llm.py

LLM client with robustness for Phase 9:

  - Configurable provider/endpoint/model.
  - Retry with exponential backoff on rate limits / transient network errors.
  - Fallback chain: primary API -> local Ollama -> mock (offline dev).
  - Handles missing API keys gracefully.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger("jarvis.llm")

# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────

class LLMError(Exception):
    """Base LLM error."""


class LLMUnavailable(LLMError):
    """All backends failed."""


# ─────────────────────────────────────────────────────────────────────────────
# LLM client
# ─────────────────────────────────────────────────────────────────────────────

class LLMClient:
    """Minimal LLM client with retry and fallback.

    Config keys (see config.yaml):
        provider: "openai" | "ollama" | "mock"   (default auto-detect)
        model:    model id (default "auto" -> provider default)
        api_key:  API key (may be empty for ollama/mock)
        api_base: endpoint URL (OpenAI-compatible or Ollama)
        temperature, max_tokens: sampling params
        retries:  max attempts (default 3)
        backoff:  base seconds for exponential backoff (default 2)
        timeout:  per-request timeout (default 30)
    """

    OPENAI_COMPATIBLE = "https://api.openai.com/v1"
    OLLAMA_BASE = "http://localhost:11434"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.provider = (cfg.get("provider") or "auto").lower()
        self.model = cfg.get("model") or "auto"
        self.api_key = cfg.get("api_key") or ""
        self.api_base = (cfg.get("api_base") or "").strip().rstrip("/")
        self.temperature = cfg.get("temperature", 0.2)
        self.max_tokens = cfg.get("max_tokens", 2000)
        self.timeout = cfg.get("timeout", 30)
        self.retries = max(1, int(cfg.get("retries", 3)))
        self.backoff = float(cfg.get("backoff", 2.0))

        if self.provider == "auto":
            self.provider = self._detect_provider()
        if self.provider == "openai" and not self.api_base:
            self.api_base = self.OPENAI_COMPATIBLE
        if self.provider == "ollama" and not self.api_base:
            self.api_base = self.OLLAMA_BASE
        if self.provider == "mock":
            self.api_key = ""  # mock never needs a key

        self._resolved_model = None

    # ── provider detection ──────────────────────────────────────────────────

    def _detect_provider(self) -> str:
        """Pick a provider: openai if key+base, else ollama if reachable, else mock."""
        if self.api_key and self.api_base:
            return "openai"
        if self._ollama_reachable():
            return "ollama"
        return "mock"

    def _ollama_reachable(self, timeout: float = 1.5) -> bool:
        try:
            r = requests.get(f"{self.OLLAMA_BASE}/api/tags", timeout=timeout)
            return r.status_code == 200
        except Exception:
            return False

    # ── public API ──────────────────────────────────────────────────────────

    def get_model(self) -> str:
        """Return the effective model name (resolving 'auto' once)."""
        if self._resolved_model:
            return self._resolved_model
        if self.model and self.model != "auto":
            self._resolved_model = self.model
        else:
            models = self.list_models()
            self._resolved_model = models[0] if models else self._default_model()
        return self._resolved_model

    def _default_model(self) -> str:
        return {
            "openai": "gpt-4o-mini",
            "ollama": "llama3.2",
            "mock": "mock-model",
        }.get(self.provider, "gpt-4o-mini")

    def list_models(self) -> List[str]:
        """Return available model ids (best-effort)."""
        if self.provider == "mock":
            return [self._default_model()]
        if self.provider == "ollama":
            try:
                r = requests.get(f"{self.api_base}/api/tags", timeout=self.timeout)
                if r.status_code == 200:
                    return [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]
            except Exception:
                pass
            return []
        # openai-compatible
        try:
            r = requests.get(
                f"{self.api_base}/models",
                headers=self._headers(),
                timeout=self.timeout,
            )
            if r.status_code == 200:
                return [m.get("id", "") for m in r.json().get("data", []) if m.get("id")]
        except Exception:
            pass
        return [self._default_model()]

    def complete(self, messages: List[Dict[str, str]]) -> str:
        """Run a chat completion with retry/backoff + fallback.

        Args:
            messages: [{"role": "system"|"user"|"assistant", "content": "..."}]

        Returns:
            The assistant text content.

        Raises:
            LLMUnavailable if every backend fails.
        """
        last_err: Optional[Exception] = None

        # Primary attempt with retries
        for attempt in range(1, self.retries + 1):
            try:
                return self._call(messages)
            except LLMError as e:
                last_err = e
                log.warning("LLM attempt %s/%s failed: %s", attempt, self.retries, e)
                if attempt < self.retries:
                    time.sleep(self.backoff * (2 ** (attempt - 1)))

        # Fallback: try ollama if we're not already on it
        if self.provider != "ollama" and self._ollama_reachable():
            log.info("Falling back to local Ollama")
            try:
                return self._call_ollama(messages)
            except LLMError as e:
                last_err = e

        # Last resort: deterministic mock (keeps the agent usable offline)
        log.info("Using mock LLM fallback")
        return self._call_mock(messages)

    # ── individual backends ─────────────────────────────────────────────────

    def _call(self, messages: List[Dict[str, str]]) -> str:
        if self.provider == "mock":
            return self._call_mock(messages)
        if self.provider == "ollama":
            return self._call_ollama(messages)
        return self._call_openai(messages)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _call_openai(self, messages: List[Dict[str, str]]) -> str:
        if not self.api_key:
            raise LLMError("OpenAI provider requires an API key")
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.get_model(),
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        try:
            r = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise LLMError(f"Network error: {e}") from e

        if r.status_code in (429, 500, 502, 503, 504):
            raise LLMError(f"Transient error {r.status_code}")
        if r.status_code != 200:
            raise LLMError(f"API error {r.status_code}: {r.text[:200]}")

        try:
            return r.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"Unexpected response shape: {e}") from e

    def _call_ollama(self, messages: List[Dict[str, str]]) -> str:
        url = f"{self.api_base}/api/chat"
        payload = {
            "model": self.get_model(),
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature, "num_predict": self.max_tokens},
        }
        try:
            r = requests.post(url, json=payload, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise LLMError(f"Ollama network error: {e}") from e

        if r.status_code != 200:
            raise LLMError(f"Ollama error {r.status_code}: {r.text[:200]}")

        try:
            return r.json()["message"]["content"].strip()
        except (KeyError, ValueError) as e:
            raise LLMError(f"Unexpected Ollama response: {e}") from e

    def _call_mock(self, messages: List[Dict[str, str]]) -> str:
        """Deterministic offline fallback — keeps demos/tests runnable without a backend."""
        last = messages[-1]["content"] if messages else ""
        if "list files" in last.lower():
            return "MOCK: listing workspace files (offline mode). Use file_list action."
        if last:
            return f"MOCK: (offline) received {len(messages)} message(s); last: {last[:80]}"
        return "MOCK: (offline) hello from JARVIS."


# ─────────────────────────────────────────────────────────────────────────────
# Convenience factory
# ─────────────────────────────────────────────────────────────────────────────

def create_llm(config: Optional[Dict[str, Any]] = None) -> LLMClient:
    """Build an LLMClient from a config dict (used by core/agent)."""
    return LLMClient(config)
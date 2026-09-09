"""
LLM client — untrusted planner interface.

The LLM is a PLANNER, not an executor.
It produces structured JSON plans which are validated by the tool registry
and authorized by the policy engine before any execution happens.

Providers: openai-compatible, ollama, mock.
"""

import json
import logging
import time
import urllib.request
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.llm")


class LLMError(Exception):
    """Raised when all providers fail."""


def retry_with_backoff(func, retries: int = 3, backoff: float = 2.0):
    """Call func with exponential backoff on transient failures."""
    delay = backoff
    last_error = None
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                log.warning("LLM call failed (attempt %d/%d): %s — retrying in %.1fs",
                            attempt + 1, retries, e, delay)
                time.sleep(delay)
                delay *= 2
    raise LLMError(f"LLM call failed after {retries} attempts: {last_error}")


class OpenAICompatProvider:
    """OpenAI-compatible HTTP API client."""

    def __init__(self, api_key: str = "", api_base: str = "", model: str = "",
                 temperature: float = 0.2, max_tokens: int = 2000, timeout: int = 30):
        self.api_key = api_key
        self.api_base = api_base or "https://api.openai.com/v1"
        self.model = model or "gpt-4o-mini"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request, return the assistant text."""
        url = f"{self.api_base.rstrip('/')}/chat/completions"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        import urllib.request
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"), headers=headers
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


class OllamaProvider:
    """Local Ollama provider."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "",
                 temperature: float = 0.2, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.model = model or "llama3"
        self.temperature = temperature
        self.timeout = timeout

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/api/chat"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["message"]["content"]


class MockProvider:
    """Deterministic offline provider — never makes a network call.

    Used for tests and offline development.
    """

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        # Parse the user prompt for a simple tool invocation
        text = user_prompt.lower()
        if "list" in text and ("file" in text or "folder" in text):
            return '```json\n{"tool": "filesystem.list", "arguments": {"path": "."}}\n```'
        if "create" in text or "write" in text or "make" in text:
            return '```json\n{"tool": "filesystem.write", "arguments": {"path": "output.md", "content": "Created by JARVIS"}}\n```'
        if "read" in text:
            return '```json\n{"tool": "filesystem.read", "arguments": {"path": "output.md"}}\n```'
        if "search" in text and "web" in text:
            return '```json\n{"tool": "internet.search", "arguments": {"query": "' + "weather" + '"}}\n```'
        return "I can help with that. Let me check the local system first."


class LLMClient:
    """Unified LLM client with provider fallback.

    The LLM is an UNTRUSTED planner. Its output is always validated
    before any action is executed.
    """

    def __init__(
        self,
        provider: str = "auto",
        model: str = "auto",
        api_key: str = "",
        api_base: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2000,
        retries: int = 3,
        backoff: float = 2.0,
        timeout: int = 30,
    ):
        self.provider_name = provider
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.retries = retries
        self.backoff = backoff
        self.timeout = timeout
        self.active_provider = None

        self._providers: List[Any] = []
        self._build_providers(provider, model, api_key, api_base, timeout)

    def _build_providers(self, provider, model, api_key, api_base, timeout):
        """Build the provider list in priority order."""
        resolved_model = None if model == "auto" else model

        if provider in ("auto", "openai", "ollama"):
            if api_key or api_base:
                self._providers.append(OpenAICompatProvider(
                    api_key=api_key, api_base=api_base, model=resolved_model or "",
                    temperature=self.temperature, max_tokens=self.max_tokens, timeout=timeout,
                ))
            if provider in ("auto", "ollama"):
                self._providers.append(OllamaProvider(
                    model=resolved_model or "", temperature=self.temperature, timeout=timeout,
                ))
        # Mock is always the last fallback so offline mode never crashes
        self._providers.append(MockProvider())

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Get a completion from the best available provider.

        Falls through providers in priority order. Never raises for
        offline development (mock is always last).
        """
        errors = []
        for provider in self._providers:
            try:
                result = retry_with_backoff(
                    lambda p=provider: p.complete(system_prompt, user_prompt),
                    retries=self.retries,
                    backoff=self.backoff,
                )
                self.active_provider = provider.__class__.__name__
                return result
            except Exception as e:
                errors.append(f"{provider.__class__.__name__}: {e}")
                log.warning("Provider %s failed: %s", provider.__class__.__name__, e)

        log.error("All LLM providers failed: %s", errors)
        # Absolute last resort: mock (guaranteed to work offline)
        mock = MockProvider()
        self.active_provider = "MockProvider"
        return mock.complete(system_prompt, user_prompt)
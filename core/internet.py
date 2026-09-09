"""
JARVIS OS — core/internet.py

Web access for Phase 9 with the scheme allowlist fix.

Security: only http/https URLs are accepted — file://, ftp:// and other
schemes are rejected outright (fixes the src/internet.py gap where any
scheme with a netloc passed validation).
"""

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("jarvis.internet")

ALLOWED_SCHEMES = {"http", "https"}
DEFAULT_TIMEOUT = 30


class InternetError(Exception):
    """Raised for invalid URLs or fetch failures."""


class Internet:
    """HTTP(S)-only web access with on-demand enable/disable + research storage."""

    def __init__(self, research_path: str = "workspace/research"):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.research_dir = os.path.realpath(os.path.join(project_root, research_path))
        os.makedirs(self.research_dir, exist_ok=True)
        self.enabled = True
        self.requires_approval = True

    # ── state ───────────────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        return self.enabled

    def enable(self) -> str:
        self.enabled = True
        return "🌐 Internet access enabled."

    def disable(self) -> str:
        self.enabled = False
        return "🌐 Internet access disabled."

    # ── URL validation (scheme allowlist) ───────────────────────────────────

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Only http/https URLs are valid for JARVIS."""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ALLOWED_SCHEMES and bool(parsed.netloc)
        except Exception:
            return False

    def _require_url(self, url: str) -> str:
        if not self.is_valid_url(url):
            raise InternetError(f"Blocked URL scheme: {url[:80]!r} (only http/https allowed)")
        return url

    # ── fetching ────────────────────────────────────────────────────────────

    def _fetch(self, url: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[Optional[str], Optional[str]]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        try:
            r = requests.get(url, headers=headers, timeout=timeout, verify=False)
            r.raise_for_status()
            return r.text, None
        except requests.exceptions.Timeout:
            return None, "Request timed out."
        except requests.exceptions.HTTPError as e:
            return None, f"HTTP error: {e.response.status_code}"
        except Exception as e:
            return None, str(e)

    @staticmethod
    def _extract_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return "\n".join(lines)

    # ── public API ──────────────────────────────────────────────────────────

    def browse(self, url: str, max_chars: int = 4000) -> Dict[str, Any]:
        """Fetch a URL and return extracted text."""
        if not self.enabled:
            return {"success": False, "error": "Internet access is disabled"}
        try:
            self._require_url(url)
        except InternetError as e:
            return {"success": False, "error": str(e)}
        html, err = self._fetch(url)
        if err is not None:
            return {"success": False, "error": err}
        text = self._extract_text(html or "")
        # Auto-save research excerpt
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        fname = re.sub(r"[^\w\-.]", "_", urlparse(url).netloc) + f"_{stamp}.md"
        try:
            with open(os.path.join(self.research_dir, fname), "w", encoding="utf-8") as f:
                f.write(f"# Research: {url}\n\n{text[:max_chars]}\n")
        except OSError as e:
            log.warning("Could not save research: %s", e)
        return {
            "success": True,
            "url": url,
            "content": text[:max_chars],
            "saved": os.path.join(self.research_dir, fname),
        }

    def search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Search using DuckDuckGo html (no API key)."""
        if not self.enabled:
            return {"success": False, "error": "Internet access is disabled"}
        url = "https://html.duckduckgo.com/html/"
        try:
            r = requests.post(
                url,
                data={"q": query},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=DEFAULT_TIMEOUT,
            )
            r.raise_for_status()
        except Exception as e:
            return {"success": False, "error": f"Search failed: {e}"}

        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for link in soup.select("a.result__a"):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            # DDG wraps in //duckduckgo.com/l/?uddg=...
            m = re.search(r"uddg=([^&]+)", href)
            if m:
                href = requests.utils.unquote(m.group(1))
            results.append({"title": title, "url": href})
            if len(results) >= max_results:
                break
        return {"success": True, "query": query, "results": results}

    def list_research(self) -> List[str]:
        """List saved research excerpts."""
        try:
            return sorted(
                f for f in os.listdir(self.research_dir)
                if f.endswith(".md") and f != "index.md"
            )
        except OSError:
            return []
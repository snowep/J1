"""
Internet tool — web access with SSRF protection.

Security:
- http/https only (file://, ftp://, etc. rejected)
- TLS verification enabled (verify=True)
- Loopback/private IPv4/IPv6 blocked
- Link-local blocked
- Cloud metadata endpoint blocked (169.254.169.254)
- Redirect revalidation
- Response size limits
- Explicit timeouts
- Provenance tracking
"""

import ipaddress
import logging
import re
import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from ..agent.state import ActionResult, ActionStatus

log = logging.getLogger("jarvis.tools.internet")

ALLOWED_SCHEMES = {"http", "https"}
DEFAULT_TIMEOUT = 30
MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_REDIRECTS = 5

# Private/blocked IP ranges
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("10.0.0.0/8"),       # private
    ipaddress.ip_network("172.16.0.0/12"),    # private
    ipaddress.ip_network("192.168.0.0/16"),   # private
    ipaddress.ip_network("169.254.0.0/16"),   # link-local + cloud metadata
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 private
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]


def _is_ip_blocked(hostname: str) -> bool:
    """Check if a hostname resolves to a blocked IP range."""
    try:
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            addr_str = info[4][0]
            try:
                addr = ipaddress.ip_address(addr_str)
                for net in _BLOCKED_NETWORKS:
                    if addr in net:
                        return True
            except ValueError:
                continue
    except (socket.gaierror, OSError):
        return False
    return False


class InternetTool:
    """HTTP(S)-only web access with SSRF protection and provenance tracking."""

    def __init__(self, workspace: str = "workspace"):
        self.workspace = workspace
        self.enabled = True

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Only http/https URLs are valid."""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ALLOWED_SCHEMES and bool(parsed.netloc)
        except Exception:
            return False

    def _validate_url(self, url: str) -> Optional[str]:
        """Full URL validation including scheme and SSRF checks.

        Returns error message if invalid, None if valid.
        """
        if not self.is_valid_url(url):
            return f"Invalid URL scheme or format: {url}"

        parsed = urlparse(url)

        # Block loopback / private / metadata IPs
        hostname = parsed.hostname
        if hostname and _is_ip_blocked(hostname):
            return f"Blocked: {hostname} resolves to a private/loopback/metadata address"

        return None

    def search(self, query: str, max_results: int = 5) -> ActionResult:
        """Search the web for information.

        Uses a simple web search approach.
        """
        if not self.enabled:
            return ActionResult(
                success=False,
                error="Internet access is disabled",
                status=ActionStatus.FAILED,
            )

        # Use DuckDuckGo HTML search as a lightweight option
        search_url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"

        error = self._validate_url(search_url)
        if error:
            return ActionResult(success=False, error=error, status=ActionStatus.FAILED)

        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; JARVIS-OS/1.0)"}
            response = requests.get(
                search_url,
                headers=headers,
                timeout=DEFAULT_TIMEOUT,
                verify=True,
                allow_redirects=True,
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            for result_div in soup.select(".result")[:max_results]:
                title_el = result_div.select_one(".result__a")
                snippet_el = result_div.select_one(".result__snippet")
                if title_el:
                    results.append({
                        "title": title_el.get_text(strip=True),
                        "url": title_el.get("href", ""),
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    })

            output = f"Search results for: {query}\n\n"
            for i, r in enumerate(results, 1):
                output += f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}\n\n"

            return ActionResult(
                success=True,
                output=output,
                status=ActionStatus.SUCCESS,
                metadata={"query": query, "results": results, "result_count": len(results)},
            )
        except requests.exceptions.Timeout:
            return ActionResult(success=False, error="Search timed out", status=ActionStatus.FAILED)
        except requests.exceptions.RequestException as e:
            return ActionResult(success=False, error=f"Search failed: {e}", status=ActionStatus.FAILED)

    def fetch(self, url: str, timeout: int = DEFAULT_TIMEOUT) -> ActionResult:
        """Fetch and extract text from a URL.

        Validates URL, checks SSRF, fetches with TLS, extracts readable text.
        """
        if not self.enabled:
            return ActionResult(
                success=False,
                error="Internet access is disabled",
                status=ActionStatus.FAILED,
            )

        error = self._validate_url(url)
        if error:
            return ActionResult(success=False, error=error, status=ActionStatus.FAILED)

        start_time = datetime.now(timezone.utc)
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; JARVIS-OS/1.0)"}
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                verify=True,  # TLS verification enabled
                allow_redirects=True,
            )
            response.raise_for_status()

            # Check response size
            if len(response.content) > MAX_RESPONSE_SIZE:
                return ActionResult(
                    success=False,
                    error=f"Response too large ({len(response.content)} bytes, limit {MAX_RESPONSE_SIZE})",
                    status=ActionStatus.FAILED,
                )

            # Revalidate redirect destination
            if response.history:
                final_url = response.url
                if not self.is_valid_url(final_url):
                    return ActionResult(
                        success=False,
                        error=f"Redirect to invalid URL: {final_url}",
                        status=ActionStatus.FAILED,
                    )
                parsed_final = urlparse(final_url)
                if parsed_final.hostname and _is_ip_blocked(parsed_final.hostname):
                    return ActionResult(
                        success=False,
                        error=f"Redirect to blocked address: {parsed_final.hostname}",
                        status=ActionStatus.FAILED,
                    )

            # Extract text
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)

            # Truncate to reasonable size
            if len(text) > 50000:
                text = text[:50000] + "\n\n[Truncated]"

            return ActionResult(
                success=True,
                output=text,
                status=ActionStatus.SUCCESS,
                metadata={
                    "url": url,
                    "final_url": response.url,
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "retrieved_at": start_time.isoformat(),
                    "title": soup.title.string if soup.title else "",
                },
            )
        except requests.exceptions.Timeout:
            return ActionResult(success=False, error=f"Fetch timed out after {timeout}s", status=ActionStatus.FAILED)
        except requests.exceptions.RequestException as e:
            return ActionResult(success=False, error=f"Fetch failed: {e}", status=ActionStatus.FAILED)

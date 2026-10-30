"""Compliant HTTP infrastructure (Requirement 1.4, 1.5). Respects robots.txt,
rate limit, backoff retries. No bypassing of login/CAPTCHA/terms."""

from __future__ import annotations

import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlsplit

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


class SourceSkipped(Exception):
    """Source to skip (robots/login/terms)."""


@dataclass
class HttpClient:
    user_agent: str
    timeout: int = 20
    rate_limit_seconds: float = 1.0
    max_retries: int = 3
    _last_request: float = 0.0

    def __post_init__(self):
        self._robots_cache: dict = {}

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last_request = time.monotonic()

    def can_fetch(self, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        rp = self._robots_cache.get(base)
        if rp is None and base not in self._robots_cache:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{base}/robots.txt")
            try:
                rp.read()
            except Exception:
                rp = None
            self._robots_cache[base] = rp
        if rp is None:
            return True
        return rp.can_fetch(self.user_agent, url)

    def get(self, url: str, params: dict | None = None,
            headers: dict | None = None, check_robots: bool = True) -> str:
        if requests is None:
            raise RuntimeError("The 'requests' library is not installed.")
        if check_robots and not self.can_fetch(url):
            raise SourceSkipped(f"robots.txt disallows access to {url}")

        hdrs = {"User-Agent": self.user_agent}
        if headers:
            hdrs.update(headers)
        last_exc = None
        for attempt in range(self.max_retries):
            self._respect_rate_limit()
            try:
                resp = requests.get(url, params=params, headers=hdrs, timeout=self.timeout)
                if resp.status_code in (401, 403):
                    raise SourceSkipped(f"Access denied ({resp.status_code}) to {url}")
                resp.raise_for_status()
                return resp.text
            except SourceSkipped:
                raise
            except Exception as exc:
                last_exc = exc
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"Request failed after {self.max_retries} retries: {last_exc}")

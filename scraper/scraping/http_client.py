"""Polite HTTP client with retries, rate limiting and browser impersonation.

Moneycontrol sits behind an Akamai edge that rejects requests whose TLS
fingerprint does not match a real browser (plain ``requests``/``urllib`` get
HTTP 403 regardless of headers). ``curl_cffi`` impersonates Chrome's TLS
stack, which passes. The same client also fetches the NSE archive CSVs.

Behaviour:
* a minimum delay (+ random jitter) between any two requests,
* exponential backoff retries on 403/429/5xx and network errors,
* browser-profile rotation after a 403 (fingerprint may have been flagged),
* a request counter for run statistics.
"""

from __future__ import annotations

import logging
import random
import time

from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {403, 408, 425, 429, 500, 502, 503, 504}
IMPERSONATE_PROFILES = ["chrome", "edge99", "safari"]

DEFAULT_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.moneycontrol.com/",
}


class HttpError(Exception):
    """Raised when a request keeps failing after all retries."""

    def __init__(self, url: str, message: str, status: int | None = None) -> None:
        super().__init__(f"{message} (url={url})")
        self.url = url
        self.status = status


class HttpClient:
    """Rate-limited, retrying GET client used by every scraper."""

    def __init__(
        self,
        delay_seconds: float = 1.5,
        jitter_seconds: float = 1.0,
        timeout_seconds: int = 40,
        max_retries: int = 4,
        backoff_base: float = 2.0,
    ) -> None:
        self._delay = delay_seconds
        self._jitter = jitter_seconds
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._last_request_at = 0.0
        self._profile_index = 0
        self.requests_made = 0

    # -- internals ---------------------------------------------------------------

    def _throttle(self) -> None:
        wait = self._delay + random.uniform(0, self._jitter)
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < wait:
            time.sleep(wait - elapsed)
        self._last_request_at = time.monotonic()

    def _profile(self) -> str:
        return IMPERSONATE_PROFILES[self._profile_index % len(IMPERSONATE_PROFILES)]

    def _rotate_profile(self) -> None:
        self._profile_index += 1
        logger.debug("Rotating browser profile to %s", self._profile())

    # -- public API -----------------------------------------------------------------

    def get(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        """GET a URL with throttling and retries; returns the response body."""
        merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
        last_error: str = "unknown error"
        last_status: int | None = None

        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                backoff = self._backoff_base * (2 ** (attempt - 1))
                backoff += random.uniform(0, 1)
                logger.warning(
                    "Retry %d/%d for %s in %.1fs (%s)",
                    attempt, self._max_retries, url, backoff, last_error,
                )
                time.sleep(backoff)
            self._throttle()
            self.requests_made += 1
            try:
                response = curl_requests.get(
                    url,
                    headers=merged_headers,
                    impersonate=self._profile(),
                    timeout=self._timeout,
                )
            except Exception as exc:  # curl_cffi raises its own error types
                last_error = f"network error: {exc}"
                continue

            if response.status_code == 200:
                return response.content
            last_status = response.status_code
            last_error = f"HTTP {response.status_code}"
            if response.status_code == 403:
                self._rotate_profile()
            if response.status_code not in RETRYABLE_STATUS:
                break  # 404 and friends will not improve with retries

        raise HttpError(url, last_error, last_status)

    def get_text(self, url: str, encoding: str = "utf-8") -> str:
        return self.get(url).decode(encoding, errors="replace")

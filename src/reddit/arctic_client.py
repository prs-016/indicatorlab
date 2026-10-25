"""Polite HTTP client for the Arctic Shift API.

- Enforces a minimum interval between requests (default ~1s).
- Retries with exponential backoff on network errors, HTTP 429/5xx, and the
  API's in-body rate-limit message ("Timeout. Maybe slow down a bit"), which is
  returned with HTTP 200 and `data: null`, so the body must be inspected.
- Never converts a failure into an empty result: exhausted retries raise.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode

import requests

from src.reddit import settings
from src.reddit.utils import get_logger, utc_now_iso

log = get_logger("arctic_client", "collect_reddit.log")


def _is_rate_limit_text(text: str) -> bool:
    t = text[:500].lower()
    return "slow down" in t or "timeout" in t


class ArcticShiftError(RuntimeError):
    def __init__(self, msg: str, attempts: list[dict]):
        super().__init__(msg)
        self.attempts = attempts


@dataclass
class ApiResult:
    url: str
    params: dict
    http_status: int
    retrieved_at_utc: str
    body: dict
    attempts: list[dict] = field(default_factory=list)


class ArcticShiftClient:
    def __init__(
        self,
        base_url: str = settings.ARCTIC_BASE_URL,
        min_interval: float = 1.0,
        max_attempts: int = 8,
        base_backoff: float = 2.0,
        max_backoff: float = 120.0,
        timeout: float = 90.0,
        session: requests.Session | None = None,
        sleep=time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval
        self.max_attempts = max_attempts
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", "indicator-lab-reddit-research/1.0 (academic project)")
        self._sleep = sleep
        self._last_request = 0.0
        self.n_requests = 0

    def _pace(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            self._sleep(wait)

    def _backoff(self, attempt: int, retry_after: str | None = None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.max_backoff)
            except ValueError:
                pass
        return min(self.base_backoff * 2 ** (attempt - 1), self.max_backoff) + random.uniform(0, 1)

    def get(self, path: str, params: dict) -> ApiResult:
        url = f"{self.base_url}/{path.lstrip('/')}"
        full_url = f"{url}?{urlencode(params)}"
        attempts: list[dict] = []
        for attempt in range(1, self.max_attempts + 1):
            self._pace()
            ts = utc_now_iso()
            self._last_request = time.monotonic()
            self.n_requests += 1
            rec = {"attempt": attempt, "requested_at_utc": ts}
            retry_after = None
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                rec["http_status"] = r.status_code
                if r.status_code == 429 or r.status_code >= 500 or _is_rate_limit_text(r.text):
                    # The rate-limit message has been observed with HTTP 200 and HTTP 422.
                    retry_after = r.headers.get("Retry-After")
                    rec["error"] = f"HTTP {r.status_code}: {r.text[:120]}"
                elif r.status_code >= 400:
                    rec["error"] = f"HTTP {r.status_code}: {r.text[:300]}"
                    attempts.append(rec)
                    raise ArcticShiftError(f"non-retryable {rec['error']} for {full_url}", attempts)
                else:
                    try:
                        body = r.json()
                    except ValueError:
                        rec["error"] = f"invalid JSON: {r.text[:200]!r}"
                    else:
                        err = body.get("error") if isinstance(body, dict) else "non-dict body"
                        if err or not isinstance(body.get("data"), list):
                            rec["error"] = f"api error: {err!r}"
                        else:
                            attempts.append(rec)
                            return ApiResult(full_url, dict(params), r.status_code, ts, body, attempts)
            except ArcticShiftError:
                raise
            except requests.RequestException as e:
                rec["error"] = f"{type(e).__name__}: {e}"
            attempts.append(rec)
            if attempt < self.max_attempts:
                delay = self._backoff(attempt, retry_after)
                log.warning("attempt %d/%d failed (%s) for %s; sleeping %.1fs",
                            attempt, self.max_attempts, rec["error"], full_url, delay)
                self._sleep(delay)
        raise ArcticShiftError(f"gave up after {self.max_attempts} attempts: {full_url}", attempts)

"""Polite HTTP client for the Arctic Shift API.

- Enforces a minimum interval between requests (config.yaml, ~1 s).
- On network errors, HTTP 429/5xx, the in-body "Internal server error" and the API's
  in-body rate-limit message ("Timeout. Maybe slow down a bit", returned with HTTP 200
  or 422 and `data: null`, so the body must be inspected) it waits a random 10-30 s and
  retries up to 3 times (config.yaml `reddit.arctic_shift`).
- Never converts a failure into an empty result: exhausted retries raise, and the
  collector then logs the day as failed.
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

REQUEST_TIMEOUT_S = 90.0   # busy r/wallstreetbets days can take ~60 s to answer


def _is_rate_limit_text(text: str) -> bool:
    t = text[:500].lower()
    return "slow down" in t or "timeout" in t or "internal server error" in t


class ArcticShiftError(RuntimeError):
    """Raised when a request fails for good; `attempts` keeps every try's status and error."""

    def __init__(self, msg: str, attempts: list[dict]):
        super().__init__(msg)
        self.attempts = attempts


@dataclass
class ApiResult:
    """One successful API response with the request URL, parameters, status, time and attempts."""

    url: str
    params: dict
    http_status: int
    retrieved_at_utc: str
    body: dict
    attempts: list[dict] = field(default_factory=list)


class ArcticShiftClient:
    """Paced, retrying GET client for the Arctic Shift API (see the module docstring)."""

    def __init__(
        self,
        base_url: str = settings.ARCTIC_BASE_URL,
        min_interval: float = settings.ARCTIC_MIN_INTERVAL_S,
        max_attempts: int = 1 + settings.ARCTIC_MAX_RETRIES,
        retry_wait: tuple[float, float] = settings.ARCTIC_RETRY_WAIT_S,
        timeout: float = REQUEST_TIMEOUT_S,
        session: requests.Session | None = None,
        sleep=time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval
        self.max_attempts = max_attempts
        self.retry_wait = retry_wait
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
        """Seconds to wait before retry `attempt + 1`: the server's Retry-After if given, else uniform(retry_wait)."""
        lo, hi = self.retry_wait
        if retry_after:
            try:
                return min(float(retry_after), hi)
            except ValueError:
                pass
        return random.uniform(lo, hi)

    def get(self, path: str, params: dict) -> ApiResult:
        """GET `path` with `params`, retrying per the policy; raises ArcticShiftError when retries run out."""
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

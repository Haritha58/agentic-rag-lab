import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from app.discovery.classify import LocationHints

USER_AGENT = "JobPilot/0.1 (personal job search assistant; single user)"


@dataclass
class RawJob:
    source: str
    source_job_id: str
    company_name: str
    title: str
    url: str
    location: str = ""
    description: str = ""  # plain text
    apply_url: str | None = None
    posted_at: datetime | None = None
    expires_at: datetime | None = None
    hints: LocationHints = field(default_factory=LocationHints)
    salary: dict[str, Any] | None = None  # from salary.from_struct, when the source has fields for it
    company_ats: str | None = None
    company_slug: str | None = None


@dataclass
class Feed:
    """One fetchable unit, e.g. one company's board or one board search.

    `complete` feeds list every open job, so a job missing from a successful
    fetch has closed. Search feeds return a subset, so absence means nothing.
    """

    name: str
    fetch: Callable[["Http"], list[RawJob]]
    complete: bool = True


class Http:
    """httpx client with a polite per-host delay and simple retries."""

    def __init__(self, min_interval_s: float = 0.4, retries: int = 2, timeout_s: float = 30):
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout_s, follow_redirects=True)
        self.min_interval_s = min_interval_s
        self.retries = retries
        self._last: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def _wait_turn(self, host: str) -> None:
        with self._lock:
            delay = self._last[host] + self.min_interval_s - time.monotonic()
            self._last[host] = time.monotonic() + max(delay, 0)
        if delay > 0:
            time.sleep(delay)

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        host = urlparse(url).netloc
        for attempt in range(self.retries + 1):
            self._wait_turn(host)
            try:
                resp = self.client.get(url, params=params)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
                resp.raise_for_status()
                return resp.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                retryable = not isinstance(e, httpx.HTTPStatusError) or e.response.status_code in (429, 500, 502, 503, 504)
                if attempt == self.retries or not retryable:
                    raise
                time.sleep(1.5 * (attempt + 1))

    def close(self) -> None:
        self.client.close()


def parse_dt(value: Any) -> datetime | None:
    """ISO strings, epoch seconds or epoch milliseconds."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > 10**11 else value
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError):
        return None

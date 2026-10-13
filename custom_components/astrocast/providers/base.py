"""Shared HTTP helpers for providers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

USER_AGENT = "AstroCast/{version} (+https://github.com/FigurinePanda43/AstroCast)"


class ProviderError(Exception):
    """A provider could not deliver usable data."""


@dataclass(slots=True)
class ProviderStatus:
    """Health of a provider, exposed for transparency and diagnostics."""

    name: str
    ttl: timedelta
    last_success: datetime | None = None
    last_attempt: datetime | None = None
    last_error: str | None = None
    failures: int = 0
    next_attempt: datetime | None = None

    def due(self, now: datetime) -> bool:
        """Whether the provider should be queried now."""
        if self.next_attempt is not None and now < self.next_attempt:
            return False
        if self.last_success is None:
            return True
        return now - self.last_success >= self.ttl

    def record_success(self, now: datetime) -> None:
        """Mark a successful fetch."""
        self.last_success = now
        self.last_attempt = now
        self.last_error = None
        self.failures = 0
        self.next_attempt = None

    def record_failure(self, now: datetime, error: str) -> None:
        """Mark a failed fetch and schedule an exponential back-off."""
        self.last_attempt = now
        self.last_error = error
        self.failures += 1
        delay = min(timedelta(minutes=5) * (2 ** (self.failures - 1)), timedelta(hours=3))
        self.next_attempt = now + delay

    def stale(self, now: datetime, factor: float = 3.0) -> bool:
        """Data older than ``factor`` × TTL is considered stale."""
        return self.last_success is None or now - self.last_success > self.ttl * factor

    def as_dict(self) -> dict[str, Any]:
        """Serialise."""
        return {
            "name": self.name,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
            "last_error": self.last_error,
            "failures": self.failures,
            "next_attempt": self.next_attempt.isoformat() if self.next_attempt else None,
        }


async def fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
    retries: int = 1,
) -> Any:
    """GET a JSON document with a timeout and a short retry on transient errors."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            async with session.get(
                url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status == 429:
                    raise ProviderError("rate limited (HTTP 429)")
                if 400 <= response.status < 500:
                    text = (await response.text())[:300]
                    raise ProviderError(f"HTTP {response.status}: {text}")
                response.raise_for_status()
                # 7Timer! serves JSON with a text/html content type.
                return await response.json(content_type=None)
        except ProviderError:
            raise
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            last_error = err
            if attempt < retries:
                await asyncio.sleep(2.0 * (attempt + 1))
    raise ProviderError(f"{type(last_error).__name__}: {last_error}") from last_error


def utcnow() -> datetime:
    """Current UTC time (patched in tests)."""
    return datetime.now(UTC)

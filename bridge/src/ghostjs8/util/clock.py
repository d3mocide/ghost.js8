"""Injectable clocks. Anything time-dependent takes a Clock so tests are deterministic."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float:
        """Seconds from an arbitrary origin; never goes backwards."""
        ...

    def utc_now(self) -> datetime:
        """Wall-clock time, timezone-aware UTC."""
        ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def utc_now(self) -> datetime:
        return datetime.now(UTC)


class ManualClock:
    """A clock that only moves when told to. For tests and simulations."""

    def __init__(self, start: datetime | None = None) -> None:
        self._mono = 1000.0
        self._utc = start or datetime(2026, 1, 1, tzinfo=UTC)

    def monotonic(self) -> float:
        return self._mono

    def utc_now(self) -> datetime:
        return self._utc

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("ManualClock cannot go backwards")
        self._mono += seconds
        self._utc += timedelta(seconds=seconds)

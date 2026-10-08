"""Jittered exponential backoff for reconnecting to public receivers politely."""

from __future__ import annotations

import random
from collections.abc import Callable


class Backoff:
    def __init__(
        self,
        *,
        minimum_s: float = 5.0,
        maximum_s: float = 300.0,
        factor: float = 2.0,
        jitter: float = 0.25,
        rand: Callable[[], float] = random.random,
    ) -> None:
        if not 0 < minimum_s <= maximum_s:
            raise ValueError("need 0 < minimum <= maximum")
        self._min, self._max, self._factor, self._jitter = minimum_s, maximum_s, factor, jitter
        self._rand = rand
        self._attempt = 0

    def next_delay(self) -> float:
        """Delay before the next attempt; grows until reset()."""
        base = min(self._max, self._min * self._factor**self._attempt)
        self._attempt += 1
        spread = base * self._jitter
        return max(self._min, min(self._max, base - spread + 2 * spread * self._rand()))

    def reset(self) -> None:
        self._attempt = 0

"""Sliding-window rate limiting keyed by client address (bounded memory)."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping

from ghostjs8.util.clock import Clock


class KeyedLimiter:
    """At most ``limit`` events per ``window_s`` per key; the key table is bounded."""

    def __init__(self, clock: Clock, limit: int, window_s: float, *, max_keys: int = 4096) -> None:
        self._clock, self._limit, self._window = clock, limit, window_s
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}

    def _live(self, key: str) -> deque[float]:
        now = self._clock.monotonic()
        q = self._hits.get(key)
        if q is None:
            if len(self._hits) >= self._max_keys:
                self._prune(now)
                if len(self._hits) >= self._max_keys:  # still full: drop the oldest key
                    self._hits.pop(next(iter(self._hits)))
            q = self._hits[key] = deque()
        while q and now - q[0] >= self._window:
            q.popleft()
        return q

    def _prune(self, now: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] >= self._window]:
            del self._hits[k]

    def blocked(self, key: str) -> bool:
        """Is the key over its limit? Records nothing."""
        return len(self._live(key)) >= self._limit

    def hit(self, key: str) -> None:
        self._live(key).append(self._clock.monotonic())

    def allow(self, key: str) -> bool:
        """Record an event unless the key is over its limit."""
        q = self._live(key)
        if len(q) >= self._limit:
            return False
        q.append(self._clock.monotonic())
        return True

    def retry_after(self, key: str) -> int:
        q = self._live(key)
        if len(q) < self._limit:
            return 0
        return max(1, int(self._window - (self._clock.monotonic() - q[0])) + 1)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


def client_ip(headers: Mapping[str, str], peer: str | None, proxy_hops: int) -> str:
    """The viewer's address behind ``proxy_hops`` reverse proxies in front of the web container.

    The bundled nginx appends the address it saw to ``X-Forwarded-For``, so with one outer
    proxy (Caddy / NPM) the header is ``client, outer-proxy`` and the client is second from the
    end. Entries further left are attacker-controlled and ignored. A header shorter than
    expected means the deployment does not match ``GHOSTJS8_PROXY_HOPS``: fall back to the
    socket peer (everyone shares one budget, which is the safe direction).
    """
    parts = [p.strip() for p in headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if proxy_hops >= 0 and len(parts) > proxy_hops:
        return parts[-(proxy_hops + 1)]
    return peer or "unknown"

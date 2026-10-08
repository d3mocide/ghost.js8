"""Public KiwiSDR directory, fetched by the bridge and cached.

Source: the KiwiSDR.com public list as republished by rx.linkfanel.net
(``kiwisdr_com.js``: a JavaScript array literal with trailing commas). The
browser never contacts the directory itself. On refresh failure the last good
list is served marked ``stale``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.request
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

from ghostjs8.contract.messages import ReceiverDirectory, ReceiverListing
from ghostjs8.util.clock import Clock, SystemClock
from ghostjs8.util.maidenhead import normalize_grid

log = logging.getLogger("ghostjs8.receivers.directory")

DEFAULT_SOURCE = "http://rx.linkfanel.net/kiwisdr_com.js"
_TRAILING_COMMA = re.compile(r",(\s*[\]}])")
_GPS = re.compile(r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)")

Fetcher = Callable[[str], Awaitable[bytes]]


class DirectoryError(Exception):
    pass


def parse_directory(text: str) -> list[ReceiverListing]:
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        raise DirectoryError("no receiver array found")
    try:
        raw = json.loads(_TRAILING_COMMA.sub(r"\1", text[start : end + 1]))
    except json.JSONDecodeError as exc:
        raise DirectoryError(f"unparseable directory: {exc}") from exc
    if not isinstance(raw, list):
        raise DirectoryError("directory is not a list")
    out: list[ReceiverListing] = []
    for entry in raw:
        if isinstance(entry, Mapping):
            listing = _listing(entry)
            if listing is not None:
                out.append(listing)
    return out


def _int(value: object, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _listing(e: Mapping[str, Any]) -> ReceiverListing | None:
    if str(e.get("offline", "no")).lower() == "yes" or e.get("status", "active") != "active":
        return None
    url = str(e.get("url", "")).strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    tls = parts.scheme == "https"
    port = parts.port or (443 if tls else 80)
    lo, _, hi = str(e.get("bands", "0-30000000")).partition("-")
    gps = _GPS.search(str(e.get("gps", "")))
    lat, lon = (float(gps.group(1)), float(gps.group(2))) if gps else (None, None)
    if lat is not None and lon is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
        lat = lon = None
    snr = str(e.get("snr", "")).split(",")[0]
    return ReceiverListing(
        id=str(e.get("id") or f"{parts.hostname}:{port}"),
        name=str(e.get("name", "")).strip()[:200] or parts.hostname,
        host=parts.hostname,
        port=port,
        tls=tls,
        location=str(e.get("loc", "")).strip()[:200],
        grid=normalize_grid(str(e.get("grid", ""))),
        lat=lat,
        lon=lon,
        users=_int(e.get("users")),
        users_max=_int(e.get("users_max")),
        min_hz=_int(lo),
        max_hz=_int(hi, 30_000_000),
        antenna=str(e.get("antenna", "")).strip()[:200],
        snr_db=_int(snr) if snr.strip().lstrip("-").isdigit() else None,
    )


async def _http_fetch(url: str) -> bytes:
    def get() -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "ghost.js8"})  # noqa: S310
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - configured URL
            data: bytes = resp.read(16 * 2**20)
            return data

    return await asyncio.to_thread(get)


class Directory:
    def __init__(
        self,
        *,
        source: str = DEFAULT_SOURCE,
        ttl_s: float = 900.0,
        retry_s: float = 60.0,
        clock: Clock | None = None,
        fetch: Fetcher = _http_fetch,
    ) -> None:
        self._source = source
        self._ttl_s = ttl_s
        self._retry_s = retry_s
        self._clock = clock or SystemClock()
        self._fetch = fetch
        self._cached: ReceiverDirectory | None = None
        self._fetched_mono: float | None = None
        self._failed_mono: float | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> ReceiverDirectory:
        async with self._lock:
            now = self._clock.monotonic()
            fresh = self._fetched_mono is not None and now - self._fetched_mono < self._ttl_s
            recently_failed = (
                self._failed_mono is not None and now - self._failed_mono < self._retry_s
            )
            if self._cached is not None and (fresh or recently_failed):
                return self._cached
            try:
                receivers = parse_directory(
                    (await self._fetch(self._source)).decode("utf-8", "replace")
                )
            except Exception as exc:
                log.warning("receiver directory refresh failed: %s", exc)
                self._failed_mono = now
                if self._cached is None:
                    self._cached = ReceiverDirectory(
                        fetched_utc=None, stale=True, source=self._source, receivers=[]
                    )
                else:
                    self._cached = self._cached.model_copy(update={"stale": True})
                return self._cached
            self._fetched_mono, self._failed_mono = now, None
            self._cached = ReceiverDirectory(
                fetched_utc=self._clock.utc_now(),
                stale=False,
                source=self._source,
                receivers=receivers,
            )
            return self._cached

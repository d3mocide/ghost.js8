"""Pick a nearby public KiwiSDR for a given frequency.

Ranking: great-circle distance from the operator's home grid, among receivers
that cover the dial, have a free slot, and (when they report it) at least a
minimal HF SNR. Receivers that recently rejected or failed us sit out a
cooldown so we move on instead of hammering them.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from ghostjs8.contract.messages import ReceiverListing

EARTH_RADIUS_KM = 6371.0
MIN_SNR_DB = 15  # directory "snr" (HF band average); below this a receiver is mostly noise
DEFAULT_COOLDOWN = timedelta(minutes=30)
#: A receiver that connected but never sent audio is broken, not busy: leave it alone for hours.
NO_AUDIO_COOLDOWN = timedelta(hours=6)
#: Receivers that gave us audio recently are preferred over untried ones.
PROVEN_TTL = timedelta(hours=24)


PROXY_SUFFIX = ".proxy.kiwisdr.com"
PROXY_GROUP = "proxy.kiwisdr.com"


def host_group(host: str) -> str:
    """Listings that share one machine: every ``*.proxy.kiwisdr.com`` name is the same proxy host."""
    h = host.lower()
    return PROXY_GROUP if h.endswith(PROXY_SUFFIX) else h


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


@dataclass(frozen=True, slots=True)
class Candidate:
    listing: ReceiverListing
    distance_km: float

    @property
    def reason(self) -> str:
        snr = f", SNR {self.listing.snr_db} dB" if self.listing.snr_db is not None else ""
        return f"nearest free receiver: {self.distance_km:,.0f} km{snr}"


class ReceiverPicker:
    def __init__(
        self, home: tuple[float, float], *, cooldown: timedelta = DEFAULT_COOLDOWN
    ) -> None:
        self.home = home
        self._cooldown = cooldown
        self._benched: dict[str, datetime] = {}
        self._proven: dict[str, datetime] = {}

    def bench(self, listing_id: str, now: datetime, cooldown: timedelta | None = None) -> None:
        """Skip this receiver until the cooldown expires (it rejected or failed us)."""
        self._benched[listing_id] = now + (cooldown or self._cooldown)
        self._proven.pop(listing_id, None)

    def mark_proven(self, listing_id: str, now: datetime) -> None:
        """This receiver has delivered audio for a while: prefer it next time."""
        self._proven[listing_id] = now

    def is_proven(self, listing_id: str, now: datetime) -> bool:
        seen = self._proven.get(listing_id)
        return seen is not None and now - seen < PROVEN_TTL

    def bench_host(self, host: str, now: datetime) -> None:
        """Skip every listing on this machine (it was unreachable, so its siblings are too)."""
        self._benched[f"host:{host_group(host)}"] = now + self._cooldown

    def rank(
        self, receivers: Iterable[ReceiverListing], dial_hz: int, now: datetime
    ) -> list[Candidate]:
        self._benched = {k: v for k, v in self._benched.items() if v > now}
        out: list[Candidate] = []
        for r in receivers:
            if (
                r.id in self._benched
                or f"host:{host_group(r.host)}" in self._benched
                or r.lat is None
                or r.lon is None
            ):
                continue
            if not (r.min_hz <= dial_hz and dial_hz + 3000 <= r.max_hz):
                continue
            if r.users_max > 0 and r.users >= r.users_max:
                continue
            if r.snr_db is not None and r.snr_db < MIN_SNR_DB:
                continue
            out.append(Candidate(r, distance_km(self.home[0], self.home[1], r.lat, r.lon)))
        # Direct receivers first: a proxied one is only a fallback, and a dead proxy host
        # takes all of its listings down at once.
        return sorted(
            out,
            key=lambda c: (
                host_group(c.listing.host) == PROXY_GROUP,
                not self.is_proven(c.listing.id, now),
                c.distance_km,
                -(c.listing.snr_db or 0),
            ),
        )

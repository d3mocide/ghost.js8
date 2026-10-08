"""The GhostNet v1.5 JS8Call comm windows, as data.

Source: "GhostNet Version 1.5", S2 Underground (CC BY-NC-SA 4.0), pages 12-18.
Only the JS8Call windows are listed; Winlink, RTTY, ALE and voice windows are
other modes this project does not decode.

All times are UTC. The North America "Thursday night" net is Friday 01:00 UTC.
GhostNet's 40 m JS8 frequency is 7.107 MHz, deliberately *not* JS8Call's
standard 7.078 MHz.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, time, timedelta

GHOSTNET_40M_HZ = 7_107_000
GHOSTNET_20M_HZ = 14_107_000
GHOSTNET_80M_HZ = 3_575_000

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


class Region(enum.StrEnum):
    NA = "na"
    EU = "eu"
    AUS = "aus"


@dataclass(frozen=True, slots=True)
class NetWindow:
    id: str
    label: str
    kind: str  # "net" | "bridge"
    weekday: int  # UTC weekday, Monday = 0
    start: time  # UTC
    minutes: int
    dial_hz: int
    band: str
    regions: frozenset[Region]

    def occurrence_from(self, now: datetime) -> Occurrence:
        """The occurrence that is in progress at ``now`` or starts after it."""
        day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        days = (self.weekday - now.weekday()) % 7
        for offset in (days - 7, days, days + 7):
            start = day0 + timedelta(days=offset, hours=self.start.hour, minutes=self.start.minute)
            end = start + timedelta(minutes=self.minutes)
            if end > now:
                return Occurrence(self, start, end)
        raise AssertionError("unreachable: a weekly window always recurs within 14 days")


@dataclass(frozen=True, slots=True)
class Occurrence:
    window: NetWindow
    start: datetime
    end: datetime

    @property
    def key(self) -> str:
        """Stable id for one occurrence, e.g. ``na-thu-net@2026-10-09T01:00Z``."""
        return f"{self.window.id}@{self.start.strftime('%Y-%m-%dT%H:%MZ')}"


def _w(  # noqa: PLR0917 - compact table rows below
    id: str,
    label: str,
    kind: str,
    weekday: int,
    hh: int,
    mm: int,
    minutes: int,
    dial_hz: int,
    band: str,
    *regions: Region,
) -> NetWindow:
    return NetWindow(
        id, label, kind, weekday, time(hh, mm), minutes, dial_hz, band, frozenset(regions)
    )


NA, EU, AUS = Region.NA, Region.EU, Region.AUS

PLAN: tuple[NetWindow, ...] = (
    # Weekly nets, Thursday night local (40 m, 7.107 MHz, NVIS)
    _w("na-net", "GhostNet North America", "net", FRI, 1, 0, 30, GHOSTNET_40M_HZ, "40m", NA),
    _w("eu-net", "GhostNet Europe", "net", THU, 18, 0, 30, GHOSTNET_40M_HZ, "40m", EU),
    _w("aus-net", "GhostNet Australia", "net", THU, 7, 0, 30, GHOSTNET_40M_HZ, "40m", AUS),
    # Saturday data bridges
    _w(
        "na-eu-20m",
        "North America-Europe data bridge",
        "bridge",
        SAT,
        18,
        0,
        60,
        GHOSTNET_20M_HZ,
        "20m",
        NA,
        EU,
    ),
    _w(
        "na-aus-20m",
        "North America-Australia data bridge",
        "bridge",
        SAT,
        12,
        0,
        60,
        GHOSTNET_20M_HZ,
        "20m",
        NA,
        AUS,
    ),
    _w(
        "na-aus-80m",
        "North America-Australia data bridge (80 m)",
        "bridge",
        SAT,
        13,
        30,
        30,
        GHOSTNET_80M_HZ,
        "80m",
        NA,
        AUS,
    ),
    _w(
        "eu-aus-20m",
        "Europe-Australia data bridge",
        "bridge",
        SAT,
        20,
        0,
        60,
        GHOSTNET_20M_HZ,
        "20m",
        EU,
        AUS,
    ),
    _w(
        "eu-aus-80m",
        "Europe-Australia data bridge (80 m)",
        "bridge",
        SAT,
        21,
        30,
        30,
        GHOSTNET_80M_HZ,
        "80m",
        EU,
        AUS,
    ),
    _w(
        "aus-sp-20m",
        "Australia-South Pacific data bridge",
        "bridge",
        SAT,
        8,
        0,
        60,
        GHOSTNET_20M_HZ,
        "20m",
        AUS,
    ),
    _w(
        "aus-sp-40m",
        "Australia-South Pacific data bridge (40 m)",
        "bridge",
        SAT,
        9,
        0,
        30,
        GHOSTNET_40M_HZ,
        "40m",
        AUS,
    ),
)

# Groups worth calling out in traffic.
GROUP_GHOSTNET = "@GHOSTNET"
GROUP_FLASH = "@GSTFLASH"  # emergency flash traffic: relay to highest level HQ within range


def windows_for(region: Region) -> list[NetWindow]:
    return [w for w in PLAN if region in w.regions]


def upcoming(region: Region, now: datetime, count: int = 5) -> list[Occurrence]:
    """Occurrences in progress or upcoming, soonest first."""
    occ = sorted((w.occurrence_from(now) for w in windows_for(region)), key=lambda o: o.start)
    return occ[:count]


def active(
    region: Region, now: datetime, preroll: timedelta = timedelta(minutes=10)
) -> Occurrence | None:
    """The occurrence the station should be on now (pre-roll included), if any.

    A window in progress keeps the station until it ends, even when the next
    window's pre-roll has begun.
    """
    candidates = [
        o for o in upcoming(region, now, count=len(PLAN)) if o.start - preroll <= now < o.end
    ]
    if not candidates:
        return None
    in_progress = [o for o in candidates if o.start <= now]
    return min(in_progress or candidates, key=lambda o: o.start)

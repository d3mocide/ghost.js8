"""Maidenhead grid locators. Only valid grids are ever mapped."""

from __future__ import annotations

import re

# Field (A-R), square (0-9), optional subsquare (a-x), optional extended square (0-9).
_GRID = re.compile(r"^[A-R]{2}(?:[0-9]{2}(?:[A-X]{2}(?:[0-9]{2})?)?)?$")


def normalize_grid(grid: str | None) -> str | None:
    """Return the canonical form (AB12cd34) of a valid 2/4/6/8-character grid, else None.

    Two-character fields are rejected: too coarse to map meaningfully.
    """
    if not grid:
        return None
    g = grid.strip().upper()
    if len(g) not in (4, 6, 8) or not _GRID.match(g):
        return None
    return g[:4] + g[4:6].lower() + g[6:]


def grid_center(grid: str) -> tuple[float, float]:
    """(lat, lon) of the centre of a valid grid square. Raises ValueError otherwise."""
    g = normalize_grid(grid)
    if g is None:
        raise ValueError(f"invalid Maidenhead grid: {grid!r}")
    u = g.upper()
    lon: float = (ord(u[0]) - 65) * 20 - 180
    lat: float = (ord(u[1]) - 65) * 10 - 90
    lon += int(u[2]) * 2
    lat += int(u[3])
    lon_size, lat_size = 2.0, 1.0
    if len(u) >= 6:
        lon += (ord(u[4]) - 65) * (2 / 24)
        lat += (ord(u[5]) - 65) * (1 / 24)
        lon_size, lat_size = 2 / 24, 1 / 24
    if len(u) == 8:
        lon += int(u[6]) * (2 / 240)
        lat += int(u[7]) * (1 / 240)
        lon_size, lat_size = 2 / 240, 1 / 240
    return lat + lat_size / 2, lon + lon_size / 2

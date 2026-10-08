"""SQLite (WAL) persistence for decodes and heard stations.

Small and synchronous: a few writes per 15 s cycle. Retention is enforced by
``prune()``, which the station calls periodically.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from ghostjs8.contract.messages import Decode, NetSummary, Station
from ghostjs8.util.clock import Clock

SCHEMA = """
CREATE TABLE IF NOT EXISTS decodes (
    id INTEGER PRIMARY KEY,
    utc TEXT NOT NULL,
    json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS decodes_utc ON decodes(utc);
CREATE TABLE IF NOT EXISTS stations (
    callsign TEXT PRIMARY KEY,
    last_heard_utc TEXT NOT NULL,
    snr_db INTEGER,
    grid TEXT,
    offset_hz INTEGER,
    dial_hz INTEGER,
    heard_count INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS stations_heard ON stations(last_heard_utc);
CREATE TABLE IF NOT EXISTS nets (
    id TEXT PRIMARY KEY,
    started TEXT NOT NULL,
    json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS nets_started ON nets(started);
CREATE TABLE IF NOT EXISTS net_decodes (
    id INTEGER PRIMARY KEY,
    net_id TEXT NOT NULL REFERENCES nets(id) ON DELETE CASCADE,
    json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS net_decodes_net ON net_decodes(net_id);
"""


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class Store:
    def __init__(self, path: str | Path, clock: Clock, *, retention_days: int = 30) -> None:
        self._clock = clock
        self._retention = timedelta(days=retention_days)
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def add_decode(self, decode: Decode) -> None:
        self._db.execute(
            "INSERT INTO decodes (utc, json) VALUES (?, ?)",
            (_iso(decode.utc), decode.model_dump_json()),
        )

    def heard(
        self,
        callsign: str,
        utc: datetime,
        *,
        snr_db: int | None,
        grid: str | None,
        offset_hz: int | None,
        dial_hz: int | None,
        count: bool = True,
    ) -> Station:
        """Record a station; keeps the latest valid grid. Returns the updated row."""
        self._db.execute(
            """
            INSERT INTO stations (callsign, last_heard_utc, snr_db, grid, offset_hz, dial_hz, heard_count)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(callsign) DO UPDATE SET
                last_heard_utc = max(last_heard_utc, excluded.last_heard_utc),
                snr_db = coalesce(excluded.snr_db, snr_db),
                grid = coalesce(excluded.grid, grid),
                offset_hz = coalesce(excluded.offset_hz, offset_hz),
                dial_hz = coalesce(excluded.dial_hz, dial_hz),
                heard_count = heard_count + ?
            """,
            (callsign, _iso(utc), snr_db, grid, offset_hz, dial_hz, 1 if count else 0),
        )
        station = self.station(callsign)
        if station is None:  # pragma: no cover - just inserted
            raise RuntimeError("station vanished")
        return station

    def station(self, callsign: str) -> Station | None:
        row = self._db.execute(
            "SELECT callsign, last_heard_utc, snr_db, grid, offset_hz, dial_hz, heard_count "
            "FROM stations WHERE callsign = ?",
            (callsign,),
        ).fetchone()
        return _station(row) if row else None

    def recent_decodes(self, limit: int = 200) -> list[Decode]:
        rows = self._db.execute(
            "SELECT json FROM (SELECT id, json FROM decodes ORDER BY id DESC LIMIT ?) ORDER BY id",
            (limit,),
        ).fetchall()
        return [Decode.model_validate_json(r[0]) for r in rows]

    def stations(
        self, *, within: timedelta = timedelta(hours=24), limit: int = 500
    ) -> list[Station]:
        since = _iso(self._clock.utc_now() - within)
        rows = self._db.execute(
            "SELECT callsign, last_heard_utc, snr_db, grid, offset_hz, dial_hz, heard_count FROM stations "
            "WHERE last_heard_utc >= ? ORDER BY last_heard_utc DESC LIMIT ?",
            (since, limit),
        ).fetchall()
        return [_station(r) for r in rows]

    # ------------------------------------------------------------------ nets

    def save_net(self, net: NetSummary) -> None:
        self._db.execute(
            "INSERT INTO nets (id, started, json) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET json = excluded.json",
            (net.id, _iso(net.started), net.model_dump_json()),
        )

    def net(self, net_id: str) -> NetSummary | None:
        row = self._db.execute("SELECT json FROM nets WHERE id = ?", (net_id,)).fetchone()
        return NetSummary.model_validate_json(row[0]) if row else None

    def nets(self, limit: int = 100) -> list[NetSummary]:
        rows = self._db.execute(
            "SELECT json FROM nets ORDER BY started DESC LIMIT ?", (limit,)
        ).fetchall()
        return [NetSummary.model_validate_json(r[0]) for r in rows]

    def add_net_decode(self, net_id: str, decode: Decode) -> None:
        self._db.execute(
            "INSERT INTO net_decodes (net_id, json) VALUES (?, ?)",
            (net_id, decode.model_dump_json()),
        )

    def net_decodes(self, net_id: str) -> list[Decode]:
        rows = self._db.execute(
            "SELECT json FROM net_decodes WHERE net_id = ? ORDER BY id", (net_id,)
        ).fetchall()
        return [Decode.model_validate_json(r[0]) for r in rows]

    def expired_nets(self, older_than: timedelta) -> list[str]:
        cutoff = _iso(self._clock.utc_now() - older_than)
        return [
            r[0]
            for r in self._db.execute("SELECT id FROM nets WHERE started < ?", (cutoff,)).fetchall()
        ]

    def delete_net(self, net_id: str) -> None:
        self._db.execute("DELETE FROM net_decodes WHERE net_id = ?", (net_id,))
        self._db.execute("DELETE FROM nets WHERE id = ?", (net_id,))

    def prune(self) -> int:
        cutoff = _iso(self._clock.utc_now() - self._retention)
        removed = self._db.execute("DELETE FROM decodes WHERE utc < ?", (cutoff,)).rowcount
        removed += self._db.execute(
            "DELETE FROM stations WHERE last_heard_utc < ?", (cutoff,)
        ).rowcount
        return removed


def _station(row: tuple[object, ...]) -> Station:
    callsign, heard, snr, grid, offset, dial, count = row
    return Station(
        callsign=str(callsign),
        last_heard_utc=datetime.fromisoformat(str(heard)),
        snr_db=snr if isinstance(snr, int) else None,
        grid=grid if isinstance(grid, str) else None,
        offset_hz=offset if isinstance(offset, int) else None,
        dial_hz=dial if isinstance(dial, int) else None,
        heard_count=count if isinstance(count, int) else 1,
    )

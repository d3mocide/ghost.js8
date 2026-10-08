"""Record one GhostNet window: traffic, a waterfall image, and receiver audio.

Files live in ``<root>/<net id>/``:

- ``audio.flac``    mono 16-bit 12 kHz receiver audio, written as it arrives
- ``waterfall.png`` one row per second (newest at the bottom), audio offsets
                    -500..+3500 Hz at 10 Hz per pixel, "spectre" palette

Traffic is copied into the store per net (``net_decodes``), so a net log does
not depend on the shorter general decode retention.
"""

from __future__ import annotations

import logging
import re
import shutil
import struct
import zlib
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ghostjs8.contract.messages import Decode, NetSummary, Station
from ghostjs8.receivers.base import AUDIO_SAMPLE_RATE, AudioBlock, WaterfallRow
from ghostjs8.store.sqlite import Store
from ghostjs8.util.clock import Clock
from ghostjs8.util.maidenhead import normalize_grid

log = logging.getLogger("ghostjs8.ghostnet.recorder")

OFFSET_LO_HZ = -500
OFFSET_HI_HZ = 3500
WATERFALL_WIDTH = (OFFSET_HI_HZ - OFFSET_LO_HZ) // 10  # 10 Hz per pixel
LEVEL_FLOOR = 255 - 120  # raw u8 mapped to palette index 0 (matches the web default)
LEVEL_CEILING = 255 - 40
MAX_WATERFALL_ROWS = 4 * 3600  # hard cap: four hours at one row per second
FLASH = re.compile(r"@GSTFLASH\b", re.IGNORECASE)

# "spectre" colormap stops, identical to web/src/lib/waterfall/colormap.ts
_SPECTRE = (
    (0.0, 2, 3, 8),
    (0.3, 24, 18, 64),
    (0.55, 26, 92, 150),
    (0.72, 48, 186, 214),
    (0.86, 61, 255, 154),
    (1.0, 236, 255, 240),
)


def spectre_palette() -> bytes:
    out = bytearray()
    for i in range(256):
        t = i / 255
        k = 0
        while k < len(_SPECTRE) - 2 and t > _SPECTRE[k + 1][0]:
            k += 1
        a, b = _SPECTRE[k], _SPECTRE[k + 1]
        f = 0.0 if b[0] == a[0] else (t - a[0]) / (b[0] - a[0])
        out += bytes(round(a[c] + (b[c] - a[c]) * f) for c in (1, 2, 3))
    return bytes(out)


def encode_png_palette(rows: list[bytes], width: int, palette: bytes) -> bytes:
    """Minimal PNG (8-bit indexed colour). Stdlib only."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    height = max(1, len(rows))
    raw = b"".join(b"\x00" + r for r in rows) if rows else b"\x00" + bytes(width)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"PLTE", palette)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


class WaterfallAccumulator:
    """Reduces incoming rows to one fixed-width row per second (peak hold)."""

    def __init__(self, started: datetime, dial_hz: int, *, lsb: bool = False) -> None:
        self.started = started
        self.dial_hz = dial_hz
        self.lsb = lsb
        self.rows: list[bytes] = []
        self._current: bytearray | None = None
        self._second = -1

    def add(self, row: WaterfallRow, now: datetime) -> None:
        second = int((now - self.started).total_seconds())
        if second < 0 or second >= MAX_WATERFALL_ROWS:
            return
        if second != self._second:
            self._flush_until(second)
            self._second = second
            self._current = bytearray(WATERFALL_WIDTH)
        if self._current is None:  # pragma: no cover - set above
            return
        mapped = self._map(row)
        cur = self._current
        for x in range(WATERFALL_WIDTH):
            v = mapped[x]
            cur[x] = max(cur[x], v)

    def finish(self) -> list[bytes]:
        if self._current is not None:
            self._flush_until(self._second + 1)
        return self.rows

    def _flush_until(self, second: int) -> None:
        if self._current is not None:
            self.rows.append(bytes(self._current))
            self._current = None
        while len(self.rows) < second:
            self.rows.append(bytes(WATERFALL_WIDTH))  # gap: no rows arrived that second

    def _map(self, row: WaterfallRow) -> bytes:
        n = len(row.bins)
        out = bytearray(WATERFALL_WIDTH)
        if n == 0 or row.span_hz <= 0:
            return bytes(out)
        bins_per_hz = n / row.span_hz
        scale = 255 / (LEVEL_CEILING - LEVEL_FLOOR)
        for x in range(WATERFALL_WIDTH):
            offset = OFFSET_LO_HZ + x * 10
            lo_hz = self.dial_hz - offset - 10 if self.lsb else self.dial_hz + offset
            b0 = int((lo_hz - row.start_hz) * bins_per_hz)
            b1 = max(b0 + 1, int((lo_hz + 10 - row.start_hz) * bins_per_hz))
            if b1 <= 0 or b0 >= n:
                continue
            peak = max(row.bins[max(0, b0) : min(n, b1)])
            out[x] = min(255, max(0, round((peak - LEVEL_FLOOR) * scale)))
        return bytes(out)


AudioWriterFactory = Callable[[Path], Any]


def _open_flac(path: Path) -> Any:  # noqa: ANN401 - soundfile ships without type hints
    import soundfile  # noqa: PLC0415 - heavy import only when recording audio

    return soundfile.SoundFile(
        str(path), "w", samplerate=AUDIO_SAMPLE_RATE, channels=1, format="FLAC", subtype="PCM_16"
    )


class NetRecorder:
    """Observes a station for the length of one window."""

    def __init__(
        self,
        store: Store,
        clock: Clock,
        root: Path,
        summary: NetSummary,
        *,
        record_audio: bool = True,
        lsb: bool = False,
        open_audio: AudioWriterFactory = _open_flac,
    ) -> None:
        self.store = store
        self.clock = clock
        self.dir = root / summary.id
        self.summary = summary
        self._audio: Any = None
        self._decodes = 0
        self._flash = 0
        self._closed = False
        self.dir.mkdir(parents=True, exist_ok=True)
        if record_audio:
            try:
                self._audio = open_audio(self.dir / "audio.flac")
            except Exception:
                log.exception("audio recording unavailable; continuing without it")
        self._wf = WaterfallAccumulator(summary.started, summary.dial_hz, lsb=lsb)
        self.store.save_net(summary.model_copy(update={"has_audio": self._audio is not None}))
        log.info("recording %s (%s)", summary.label, summary.id, extra={"net": summary.id})

    # station observer -------------------------------------------------

    def on_audio(self, block: AudioBlock) -> None:
        if self._audio is not None and not self._closed:
            self._audio.buffer_write(block.pcm_s16le, dtype="int16")

    def on_waterfall(self, row: WaterfallRow) -> None:
        if not self._closed:
            self._wf.add(row, self.clock.utc_now())

    def on_decode(self, decode: Decode) -> None:
        if self._closed:
            return
        self.store.add_net_decode(self.summary.id, decode)
        self._decodes += 1
        if FLASH.search(decode.text):
            self._flash += 1

    # lifecycle ----------------------------------------------------------

    def mark_override(self) -> None:
        if not self.summary.operator_override:
            self.summary = self.summary.model_copy(update={"operator_override": True})
            self.store.save_net(self.summary)

    def set_receiver(self, receiver: str, reason: str) -> None:
        self.summary = self.summary.model_copy(
            update={"receiver": receiver, "receiver_reason": reason}
        )
        self.store.save_net(self.summary)

    def finish(self) -> NetSummary:
        if self._closed:
            return self.summary
        self._closed = True
        has_audio = False
        if self._audio is not None:
            self._audio.close()
            has_audio = (self.dir / "audio.flac").stat().st_size > 0
        rows = self._wf.finish()
        if rows:
            (self.dir / "waterfall.png").write_bytes(
                encode_png_palette(rows, WATERFALL_WIDTH, spectre_palette())
            )
        decodes = self.store.net_decodes(self.summary.id)
        self.summary = self.summary.model_copy(
            update={
                "ended": self.clock.utc_now(),
                "decode_count": len(decodes),
                "station_count": len(net_stations(self.store, decodes)),
                "flash_count": self._flash,
                "has_audio": has_audio,
                "has_waterfall": bool(rows),
            }
        )
        self.store.save_net(self.summary)
        log.info(
            "recorded %s: %d decodes", self.summary.id, len(decodes), extra={"net": self.summary.id}
        )
        return self.summary


def net_stations(store: Store, decodes: list[Decode]) -> list[Station]:
    """Stations heard in a net, from its own traffic plus known grids."""
    seen: dict[str, Station] = {}
    for d in decodes:
        call = (d.from_call or "").strip().upper()
        if not call or call.startswith("@"):
            continue
        known = store.station(call)
        prev = seen.get(call)
        grid = (
            normalize_grid(d.grid)
            or (prev.grid if prev else None)
            or (known.grid if known else None)
        )
        seen[call] = Station(
            callsign=call,
            last_heard_utc=d.utc,
            snr_db=d.snr_db,
            grid=grid,
            offset_hz=d.offset_hz,
            dial_hz=d.dial_hz,
            heard_count=(prev.heard_count + (1 if d.kind == "activity" else 0)) if prev else 1,
        )
    return sorted(seen.values(), key=lambda s: s.callsign)


def prune_recordings(store: Store, root: Path, older_than: timedelta) -> int:
    expired = store.expired_nets(older_than)
    for net_id in expired:
        shutil.rmtree(root / net_id, ignore_errors=True)
        store.delete_net(net_id)
    return len(expired)

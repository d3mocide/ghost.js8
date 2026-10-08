"""Create a synthetic recorded GhostNet window, for UI development and browser tests.

Writes a 5-minute recording of last week's net for the region: audio (quiet
hiss with JS8-like tone bursts), a waterfall image, and scripted traffic
including GhostNet check-ins and an @GSTFLASH drill. Nothing here is real
traffic; it exercises storage, the API and the net-log viewer.
"""

from __future__ import annotations

import argparse
import math
import random
import struct
from datetime import timedelta
from pathlib import Path

from ghostjs8.contract.messages import Decode, NetSummary
from ghostjs8.ghostnet.recorder import NetRecorder
from ghostjs8.ghostnet.schedule import Region, upcoming
from ghostjs8.receivers.base import AUDIO_SAMPLE_RATE, AudioBlock, WaterfallRow
from ghostjs8.store.sqlite import Store
from ghostjs8.util.clock import ManualClock, SystemClock

SECONDS = 300
SPAN_HZ = 14_648
TRAFFIC = [
    # (seconds after start, from, text after "FROM: ", grid, snr, offset)
    (20, "K0OG", "@GHOSTNET CHECKING IN EN34", "EN34", -14, 820),
    (35, "KN4CRD", "@GHOSTNET QRV EM73", "EM73", -9, 1310),
    (65, "W1GHZ", "@GHOSTNET SNR? FN31", "FN31pr", -18, 640),
    (95, "KG9B", "@GNUSAIN CHECKING IN EN52", "EN52", -12, 1720),
    (140, "W4GHT", "@GSTFLASH DRILL DRILL DRILL - EXERCISE ONLY", "EM73", -7, 1450),
    (200, "KD8SKZ", "K0OG SNR -14", None, -16, 1040),
]


def _audio_block(t: float, rng: random.Random) -> bytes:
    samples = []
    tone_on = (int(t) % 15) < 12  # JS8 transmissions fill ~12.6 s of each 15 s slot
    for i in range(512):
        x = rng.gauss(0, 18)
        if tone_on:
            x += 900 * math.sin(
                2 * math.pi * (1000 + 6.25 * (int(t * 6.25) % 8)) * (t + i / AUDIO_SAMPLE_RATE)
            )
        samples.append(max(-32768, min(32767, round(x))))
    return struct.pack(f"<{len(samples)}h", *samples)


def _wf_row(dial_hz: int, second: int) -> WaterfallRow:
    start = dial_hz + 1550 - SPAN_HZ // 2
    bins = bytearray(140 + (i * 7 + second * 13) % 9 for i in range(1024))
    for _, _, _, _, snr, offset in TRAFFIC:
        if (second % 15) < 12 and (second // 15 + offset) % 3:
            b = round((dial_hz + offset - start) * 1024 / SPAN_HZ)
            for d in range(-2, 3):
                bins[b + d] = max(bins[b + d], 205 + snr)
    return WaterfallRow(seq=second, start_hz=start, span_hz=SPAN_HZ, bins=bytes(bins))


def seed(db: Path, recordings: Path, region: Region = Region.NA) -> str:
    now = SystemClock().utc_now()
    occ = next(o for o in upcoming(region, now, 10) if o.window.kind == "net")
    occ_start, occ_end = occ.start - timedelta(days=7), occ.end - timedelta(days=7)
    clock = ManualClock(occ_start)
    store = Store(db, clock)
    w = occ.window
    nid = f"{w.id}-{occ_start.strftime('%Y%m%dT%H%MZ')}"
    if store.net(nid) is not None:
        return nid
    summary = NetSummary(
        id=nid,
        window_id=w.id,
        label=w.label,
        kind="net",
        band=w.band,
        dial_hz=w.dial_hz,
        scheduled_start=occ_start,
        scheduled_end=occ_end,
        started=occ_start,
        ended=None,
        receiver=None,
        receiver_reason="",
        decode_count=0,
        station_count=0,
        has_audio=False,
        has_waterfall=False,
        flash_count=0,
        operator_override=False,
    )
    rec = NetRecorder(store, clock, recordings, summary)
    rec.set_receiver(
        "Sample Loop Receiver (simulated)", "nearest free receiver: 0 km (seeded demo data)"
    )
    rng = random.Random(8)  # noqa: S311 - deterministic test data
    traffic = list(TRAFFIC)
    blocks_per_second = AUDIO_SAMPLE_RATE / 512
    for second in range(SECONDS):
        rec.on_waterfall(_wf_row(w.dial_hz, second))
        for k in range(round(blocks_per_second)):
            rec.on_audio(
                AudioBlock(
                    seq=0,
                    pcm_s16le=_audio_block(second + k / blocks_per_second, rng),
                    rssi_dbm=-70,
                    adc_overload=False,
                )
            )
        while traffic and traffic[0][0] <= second:
            _, frm, text, grid, snr, offset = traffic.pop(0)
            utc = clock.utc_now()
            store.heard(frm, utc, snr_db=snr, grid=grid, offset_hz=offset, dial_hz=w.dial_hz)
            rec.on_decode(
                Decode(
                    kind="activity",
                    utc=utc,
                    text=f"{frm}: {text}",
                    snr_db=snr,
                    offset_hz=offset,
                    dial_hz=w.dial_hz,
                    freq_hz=w.dial_hz + offset,
                    speed="normal",
                    from_call=frm,
                    grid=grid,
                )
            )
        clock.advance(1)
    rec.finish()
    return nid


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="seed a synthetic GhostNet recording (UI tests only)")
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--recordings", type=Path, required=True)
    p.add_argument("--region", default="na")
    args = p.parse_args(argv)
    print(seed(args.db, args.recordings, Region(args.region)))


__all__ = ["main", "seed"]

if __name__ == "__main__":
    main()

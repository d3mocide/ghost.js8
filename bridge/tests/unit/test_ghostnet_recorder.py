import struct
import zlib
from datetime import timedelta
from pathlib import Path

import soundfile

from ghostjs8.contract.messages import Decode, NetSummary
from ghostjs8.ghostnet.recorder import (
    WATERFALL_WIDTH,
    NetRecorder,
    WaterfallAccumulator,
    encode_png_palette,
    net_stations,
    prune_recordings,
    spectre_palette,
)
from ghostjs8.receivers.base import AudioBlock, WaterfallRow
from ghostjs8.store.sqlite import Store
from ghostjs8.util.clock import ManualClock

DIAL = 7_107_000


def summary(clock: ManualClock, net_id: str = "na-net-20260101T0100Z") -> NetSummary:
    now = clock.utc_now()
    return NetSummary(
        id=net_id,
        window_id="na-net",
        label="GhostNet North America",
        kind="net",
        band="40m",
        dial_hz=DIAL,
        scheduled_start=now,
        scheduled_end=now + timedelta(minutes=30),
        started=now,
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


def decode(
    clock: ManualClock, text: str, frm: str, kind: str = "activity", grid: str | None = None
) -> Decode:
    return Decode(
        kind=kind,  # type: ignore[arg-type]
        utc=clock.utc_now(),
        text=text,
        snr_db=-12,
        offset_hz=900,
        dial_hz=DIAL,
        freq_hz=DIAL + 900,
        speed="normal",
        from_call=frm,
        grid=grid,
    )


def png_dims(data: bytes) -> tuple[int, int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height, depth, color = struct.unpack(">IIBB", data[16:26])
    assert depth == 8
    return width, height, color


def wf_row_with_signal_at(offset_hz: int, value: int = 230) -> WaterfallRow:
    # 1024 bins over 14.648 kHz centred on dial + 1550 Hz (what the Kiwi adapter requests)
    span = 14_648
    start = DIAL + 1550 - span // 2
    bins = bytearray([140] * 1024)
    b = round((DIAL + offset_hz - start) * 1024 / span)
    bins[b] = value
    return WaterfallRow(seq=0, start_hz=start, span_hz=span, bins=bytes(bins))


def test_png_encoder_roundtrip() -> None:
    rows = [bytes(range(10)), bytes(10)]
    png = encode_png_palette(rows, 10, spectre_palette())
    assert png_dims(png) == (10, 2, 3)
    idat = png[png.index(b"IDAT") + 4 : png.index(b"IEND") - 8]
    assert zlib.decompress(idat) == b"\x00" + rows[0] + b"\x00" + rows[1]


def test_waterfall_accumulator_maps_offsets_and_fills_gaps() -> None:
    clock = ManualClock()
    acc = WaterfallAccumulator(clock.utc_now(), DIAL)
    acc.add(wf_row_with_signal_at(1000), clock.utc_now())
    clock.advance(3)  # seconds 1 and 2 have no rows
    acc.add(wf_row_with_signal_at(2000), clock.utc_now())
    rows = acc.finish()
    assert len(rows) == 4
    assert all(len(r) == WATERFALL_WIDTH for r in rows)
    px_1000 = (1000 + 500) // 10
    assert max(range(WATERFALL_WIDTH), key=lambda x: rows[0][x]) in (
        px_1000 - 1,
        px_1000,
        px_1000 + 1,
    )
    assert rows[1] == bytes(WATERFALL_WIDTH)  # gap row
    assert max(rows[0][px_1000 - 1 : px_1000 + 2]) > 200


def test_recorder_writes_audio_waterfall_and_traffic(tmp_path: Path) -> None:
    clock = ManualClock()
    store = Store(":memory:", clock)
    rec = NetRecorder(store, clock, tmp_path, summary(clock))
    for _ in range(24):  # ~1 s of audio
        rec.on_audio(
            AudioBlock(seq=0, pcm_s16le=b"\x10\x00" * 512, rssi_dbm=-60, adc_overload=False)
        )
    rec.on_waterfall(wf_row_with_signal_at(800))
    rec.on_decode(decode(clock, "K0OG: @GHOSTNET CHECKING IN", "K0OG"))
    clock.advance(1)
    rec.on_waterfall(wf_row_with_signal_at(1200))
    rec.on_decode(decode(clock, "W1GHZ: @GSTFLASH TEST", "W1GHZ", grid="FN31pr"))
    rec.on_decode(decode(clock, "@ALLCALL: noise", "@ALLCALL"))
    rec.set_receiver("kiwi.example:8073", "nearest free receiver: 312 km")
    clock.advance(60)
    done = rec.finish()

    assert done.ended == clock.utc_now()
    assert (done.decode_count, done.station_count, done.flash_count) == (3, 2, 1)
    assert done.has_audio
    assert done.has_waterfall
    assert done.receiver == "kiwi.example:8073"
    info = soundfile.info(str(tmp_path / done.id / "audio.flac"))
    assert (info.samplerate, info.channels, info.frames) == (12000, 1, 24 * 512)
    assert png_dims((tmp_path / done.id / "waterfall.png").read_bytes())[:2] == (WATERFALL_WIDTH, 2)
    assert store.net(done.id) == done
    assert [n.id for n in store.nets()] == [done.id]
    stations = net_stations(store, store.net_decodes(done.id))
    assert [(s.callsign, s.grid) for s in stations] == [("K0OG", None), ("W1GHZ", "FN31pr")]
    rec.on_decode(decode(clock, "late", "X1X"))  # ignored after finish
    assert len(store.net_decodes(done.id)) == 3


def test_recorder_survives_audio_failure(tmp_path: Path) -> None:
    clock = ManualClock()
    store = Store(":memory:", clock)

    def broken(_: Path) -> object:
        raise OSError("disk full")

    rec = NetRecorder(store, clock, tmp_path, summary(clock), open_audio=broken)
    rec.on_audio(AudioBlock(seq=0, pcm_s16le=b"\x00\x00", rssi_dbm=-60, adc_overload=False))
    assert not rec.finish().has_audio


def test_prune_recordings(tmp_path: Path) -> None:
    clock = ManualClock()
    store = Store(":memory:", clock)
    NetRecorder(
        store, clock, tmp_path, summary(clock, "old-20260101T0100Z"), record_audio=False
    ).finish()
    clock.advance(91 * 86400)
    NetRecorder(
        store, clock, tmp_path, summary(clock, "new-20260402T0100Z"), record_audio=False
    ).finish()
    assert prune_recordings(store, tmp_path, timedelta(days=90)) == 1
    assert [n.id for n in store.nets()] == ["new-20260402T0100Z"]
    assert not (tmp_path / "old-20260101T0100Z").exists()

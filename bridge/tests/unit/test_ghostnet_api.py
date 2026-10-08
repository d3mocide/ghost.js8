from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ghostjs8.api.app import create_app
from ghostjs8.api.hub import Hub
from ghostjs8.contract.messages import Decode, NetLog, NetSummary
from ghostjs8.decoders.base import DecoderSink
from ghostjs8.ghostnet.pilot import build_pilot
from ghostjs8.ghostnet.recorder import NetRecorder
from ghostjs8.receivers.base import AudioBlock, WaterfallRow
from ghostjs8.receivers.directory import Directory
from ghostjs8.session.station import Station
from ghostjs8.settings import Settings
from ghostjs8.store.sqlite import Store
from ghostjs8.util.clock import ManualClock

NET = "na-net-20261009T0100Z"


class FakeDecoder:
    connected = True

    def __init__(self, sink: DecoderSink) -> None:
        pass

    def submit_audio(self, pcm_s16le: bytes) -> None:
        pass

    async def run(self) -> None:
        await asyncio.Event().wait()

    async def close(self) -> None:
        pass


def recorded(tmp_path: Path) -> tuple[Station, Settings]:
    clock = ManualClock()
    store = Store(":memory:", clock)
    now = clock.utc_now()
    summary = NetSummary(
        id=NET,
        window_id="na-net",
        label="GhostNet North America",
        kind="net",
        band="40m",
        dial_hz=7_107_000,
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
    rec = NetRecorder(store, clock, tmp_path, summary)
    rec.on_audio(AudioBlock(seq=0, pcm_s16le=b"\x01\x00" * 1200, rssi_dbm=-60, adc_overload=False))
    rec.on_waterfall(
        WaterfallRow(seq=0, start_hz=7_100_000, span_hz=14_648, bins=bytes([200] * 1024))
    )
    rec.on_decode(
        Decode(
            kind="activity",
            utc=now,
            text="K0OG: @GHOSTNET QSL",
            snr_db=-9,
            offset_hz=850,
            dial_hz=7_107_000,
            freq_hz=7_107_850,
            speed="normal",
            from_call="K0OG",
        )
    )
    clock.advance(2)
    rec.finish()
    station = Station(Hub(), FakeDecoder, clock=clock, store=store)
    return station, Settings(db_path=":memory:", recordings_dir=str(tmp_path))


def test_net_endpoints(tmp_path: Path) -> None:
    station, settings = recorded(tmp_path)
    with TestClient(create_app(station, settings, directory=Directory(fetch=_no_fetch))) as http:
        nets = http.get("/api/nets").json()
        assert [NetSummary.model_validate(n).id for n in nets] == [NET]
        log = NetLog.model_validate(http.get(f"/api/nets/{NET}").json())
        assert log.summary.decode_count == 1
        assert [s.callsign for s in log.stations] == ["K0OG"]
        assert log.waterfall_seconds == 1
        assert (log.waterfall_offset_lo_hz, log.waterfall_offset_hi_hz) == (-500, 3500)
        png = http.get(f"/api/nets/{NET}/waterfall.png")
        assert png.status_code == 200
        assert png.headers["content-type"] == "image/png"
        assert png.content.startswith(b"\x89PNG")
        flac = http.get(f"/api/nets/{NET}/audio.flac")
        assert flac.status_code == 200
        assert flac.headers["content-type"] == "audio/flac"
        assert flac.content.startswith(b"fLaC")


@pytest.mark.parametrize(
    "path",
    [
        "/api/nets/nope",
        "/api/nets/na-net-20991231T0000Z",
        "/api/nets/..%2F..%2Fetc-20261009T0100Z/audio.flac",
        "/api/nets/../etc/passwd",
        "/api/nets/NA-NET-20261009T0100Z/waterfall.png",
    ],
)
def test_net_endpoints_refuse_unknown_and_traversal(tmp_path: Path, path: str) -> None:
    station, settings = recorded(tmp_path)
    with TestClient(create_app(station, settings, directory=Directory(fetch=_no_fetch))) as http:
        assert http.get(path).status_code == 404


async def _no_fetch(_: str) -> bytes:
    raise OSError("offline")


@pytest.mark.parametrize(
    ("env", "ok", "why"),
    [
        ({}, False, "off"),
        (
            {
                "GHOSTJS8_GHOSTNET": "on",
                "GHOSTJS8_GHOSTNET_REGION": "mars",
                "GHOSTJS8_HOME_GRID": "EM73",
            },
            False,
            "REGION",
        ),
        (
            {
                "GHOSTJS8_GHOSTNET": "on",
                "GHOSTJS8_GHOSTNET_REGION": "na",
                "GHOSTJS8_HOME_GRID": "ZZ99",
            },
            False,
            "HOME_GRID",
        ),
        (
            {
                "GHOSTJS8_GHOSTNET": "on",
                "GHOSTJS8_GHOSTNET_REGION": "na",
                "GHOSTJS8_HOME_GRID": "em73",
            },
            True,
            "",
        ),
    ],
)
def test_build_pilot_validation(env: dict[str, str], ok: bool, why: str) -> None:
    clock = ManualClock()
    station = Station(Hub(), FakeDecoder, clock=clock, store=Store(":memory:", clock))
    settings = Settings.from_env(env)
    pilot, reason = build_pilot(settings, station, Directory(fetch=_no_fetch), clock)
    assert (pilot is not None) is ok
    assert why in reason
    if pilot is not None:
        assert pilot.config.home_grid == "EM73"


def test_build_pilot_needs_store() -> None:
    clock = ManualClock()
    station = Station(Hub(), FakeDecoder, clock=clock)
    settings = Settings.from_env(
        {"GHOSTJS8_GHOSTNET": "on", "GHOSTJS8_GHOSTNET_REGION": "na", "GHOSTJS8_HOME_GRID": "EM73"}
    )
    pilot, reason = build_pilot(settings, station, Directory(fetch=_no_fetch), clock)
    assert pilot is None
    assert "DB_PATH" in reason

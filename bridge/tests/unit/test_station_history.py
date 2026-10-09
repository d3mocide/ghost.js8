from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from ghostjs8.api.app import create_app
from ghostjs8.api.hub import Hub
from ghostjs8.contract.messages import Decode, StationHistory
from ghostjs8.decoders.base import DecoderSink
from ghostjs8.receivers.directory import Directory
from ghostjs8.session.station import Station
from ghostjs8.settings import Settings
from ghostjs8.store.sqlite import Store
from ghostjs8.util.clock import ManualClock


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


async def _no_fetch(_: str) -> bytes:
    return b"var kiwisdr_com = [];"


def decode(clock: ManualClock, text: str, frm: str | None, to: str | None) -> Decode:
    clock.advance(15)
    return Decode(
        kind="directed" if to else "activity",
        utc=clock.utc_now(),
        text=text,
        snr_db=-12,
        offset_hz=1200,
        dial_hz=7_107_000,
        freq_hz=None,
        speed="normal",
        from_call=frm,
        to_call=to,
    )


def test_store_finds_what_a_callsign_sent_and_received() -> None:
    clock = ManualClock()
    store = Store(":memory:", clock)
    for d in (
        decode(clock, "K4JU: KQ4PDG SNR -03", "K4JU", "KQ4PDG"),
        decode(clock, "KQ4PDG: K4JU ACK", "KQ4PDG", "K4JU"),
        decode(clock, "W9ZOM: HEARTBEAT", "W9ZOM", None),
        decode(clock, "K4JU: @HB HEARTBEAT", "K4JU", None),
    ):
        store.add_decode(d)
    mine = store.station_decodes("K4JU")
    assert [d.text for d in mine] == [
        "K4JU: @HB HEARTBEAT",
        "KQ4PDG: K4JU ACK",
        "K4JU: KQ4PDG SNR -03",
    ]  # newest first, both directions
    assert store.station_counts("K4JU") == (2, 1)
    assert store.station_decodes("N0ONE") == []
    assert store.station_counts("N0ONE") == (0, 0)


def test_station_endpoint_returns_history_and_rejects_junk() -> None:
    clock = ManualClock()
    store = Store(":memory:", clock)
    store.add_decode(decode(clock, "K4JU: KQ4PDG SNR -03", "K4JU", "KQ4PDG"))
    station = Station(Hub(), FakeDecoder, clock=clock, store=store)
    settings = Settings(db_path=":memory:")
    with TestClient(create_app(station, settings, directory=Directory(fetch=_no_fetch))) as http:
        body = StationHistory.model_validate(http.get("/api/stations/k4ju").json())
        assert body.callsign == "K4JU"
        assert (body.sent, body.received) == (1, 0)
        assert len(body.decodes) == 1
        assert body.station is None  # decoded, but never recorded in `stations`
        assert http.get("/api/stations/KQ4PDG").json()["received"] == 1
        assert http.get("/api/stations/%27%3BDROP").status_code == 404
        assert http.get("/api/stations/@GHOSTNET").status_code == 404


def test_one_transmission_reported_twice_counts_once_and_keeps_the_directed_record() -> None:
    clock = ManualClock()
    store = Store(":memory:", clock)
    first = decode(clock, "KF0BSQ: WR4ITH SNR -15", "KF0BSQ", None)  # the activity line
    second = first.model_copy(update={"kind": "directed", "to_call": "WR4ITH"})  # same signal
    store.add_decode(first)
    store.add_decode(second)
    store.add_decode(decode(clock, "KF0BSQ: K4JU SNR -01", "KF0BSQ", "K4JU"))
    assert store.station_counts("KF0BSQ") == (2, 0)
    rows = store.station_decodes("KF0BSQ")
    assert [d.to_call for d in rows] == ["K4JU", "WR4ITH"]
    assert all(d.kind == "directed" for d in rows)

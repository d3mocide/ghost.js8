from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ghostjs8.api.app import create_app
from ghostjs8.api.hub import Hub, HubFull
from ghostjs8.contract.messages import Decode, Hello, server_message_adapter
from ghostjs8.decoders.base import DecodeEvent, DecoderSink
from ghostjs8.receivers.base import AudioBlock, Tuning
from ghostjs8.session.station import Station
from ghostjs8.settings import Settings
from ghostjs8.util.backoff import Backoff


class FakeDecoder:
    def __init__(self, sink: DecoderSink) -> None:
        self.sink = sink
        self.audio: list[bytes] = []

    def submit_audio(self, pcm_s16le: bytes) -> None:
        self.audio.append(pcm_s16le)

    async def run(self) -> None:
        await asyncio.Event().wait()

    async def close(self) -> None:
        pass


class FakeReceiver:
    tuning = Tuning(dial_hz=14_078_000)

    async def run(self) -> None:
        await asyncio.Event().wait()

    async def close(self) -> None:
        pass


EVENT = DecodeEvent(
    kind="directed",
    utc=datetime(2026, 10, 8, tzinfo=UTC),
    text="K0OG: KN4CRD SNR +02",
    snr_db=-22,
    offset_hz=705,
    speed="normal",
    from_call="K0OG",
    to_call="KN4CRD",
)


def test_backoff_grows_caps_and_resets() -> None:
    b = Backoff(minimum_s=5, maximum_s=300, jitter=0.0)
    delays = [b.next_delay() for _ in range(10)]
    assert delays[:4] == [5, 10, 20, 40]
    assert max(delays) == 300
    b.reset()
    assert b.next_delay() == 5


def test_backoff_jitter_stays_in_bounds() -> None:
    lo = Backoff(minimum_s=5, maximum_s=300, jitter=0.25, rand=lambda: 0.0)
    hi = Backoff(minimum_s=5, maximum_s=300, jitter=0.25, rand=lambda: 1.0)
    for _ in range(12):
        assert 5 <= lo.next_delay() <= 300
        assert 5 <= hi.next_delay() <= 300


async def test_hub_limits_and_drops_oldest() -> None:
    hub = Hub(max_clients=1, queue_size=2)
    c = hub.add()
    with pytest.raises(HubFull):
        hub.add()
    for i in range(3):
        hub.broadcast_raw(f"m{i}")
    assert c.dropped == 1
    assert [c.queue.get_nowait(), c.queue.get_nowait()] == ["m1", "m2"]
    hub.remove(c)
    assert hub.client_count == 0
    assert c.closed.is_set()


async def test_station_routes_audio_and_decodes() -> None:
    hub = Hub()
    client = hub.add()
    station = Station(hub, FakeDecoder, lambda sink: FakeReceiver())
    station.receiver = FakeReceiver()
    station.on_audio(AudioBlock(seq=1, pcm_s16le=b"\x00\x01", rssi_dbm=-60, adc_overload=False))
    assert isinstance(station.decoder, FakeDecoder)
    assert station.decoder.audio == [b"\x00\x01"]
    station.on_decode(EVENT)
    msg = server_message_adapter.validate_json(client.queue.get_nowait())
    assert isinstance(msg, Decode)
    assert (msg.text, msg.dial_hz, msg.freq_hz, msg.v) == (
        "K0OG: KN4CRD SNR +02",
        14_078_000,
        14_078_705,
        1,
    )


def test_settings_from_env() -> None:
    s = Settings.from_env(
        {
            "GHOSTJS8_RECEIVER_HOST": "kiwi.example",
            "GHOSTJS8_DIAL_HZ": "7078000",
            "GHOSTJS8_MODE": "LSB",
            "GHOSTJS8_ALLOWED_ORIGINS": "https://a, https://b",
        }
    )
    assert s.receiver_host == "kiwi.example"
    assert s.tuning == Tuning(dial_hz=7_078_000, mode="lsb")
    assert s.allowed_origins == ("https://a", "https://b")
    with pytest.raises(ValueError, match="usb or lsb"):
        Settings.from_env({"GHOSTJS8_MODE": "am"})


def test_ws_hello_then_decodes_and_cleanup() -> None:
    station = Station(Hub(), FakeDecoder)
    app = create_app(station, Settings())
    with TestClient(app) as http, http.websocket_connect("/ws") as ws:
        hello = server_message_adapter.validate_python(json.loads(ws.receive_text()))
        assert isinstance(hello, Hello)
        assert station.hub.client_count == 1
        station.on_decode(EVENT)
        decode = server_message_adapter.validate_python(json.loads(ws.receive_text()))
        assert isinstance(decode, Decode)
    assert station.hub.client_count == 0  # socket resources released on disconnect


def test_ws_origin_allowlist() -> None:
    station = Station(Hub(), FakeDecoder)
    app = create_app(station, Settings(allowed_origins=("https://ghost.example",)))
    with TestClient(app) as http:
        with (
            pytest.raises(WebSocketDisconnect),
            http.websocket_connect("/ws", headers={"origin": "https://evil"}),
        ):
            pass
        with http.websocket_connect("/ws", headers={"origin": "https://ghost.example"}) as ws:
            assert json.loads(ws.receive_text())["type"] == "hello"


def test_ws_session_full() -> None:
    station = Station(Hub(max_clients=1), FakeDecoder)
    with TestClient(create_app(station, Settings())) as http, http.websocket_connect("/ws") as ws1:
        ws1.receive_text()
        with pytest.raises(WebSocketDisconnect), http.websocket_connect("/ws"):
            pass


def test_healthz() -> None:
    with TestClient(create_app(Station(Hub(), FakeDecoder), Settings())) as http:
        assert http.get("/healthz").json() == {"status": "ok"}

from __future__ import annotations

import asyncio
import json
import struct
from dataclasses import replace
from datetime import UTC, datetime
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ghostjs8.api.app import InvalidReceiver, RateLimiter, create_app, validate_receiver_host
from ghostjs8.api.hub import Hub, HubFull
from ghostjs8.contract import binary
from ghostjs8.contract.messages import (
    Decode,
    Error,
    Health,
    Hello,
    History,
    ReceiverDirectory,
    ReceiverStatus,
    Session,
    server_message_adapter,
)
from ghostjs8.contract.messages import Station as StationMsg
from ghostjs8.decoders.base import DecodeEvent, DecoderSink, SpotEvent
from ghostjs8.receivers.base import (
    AudioBlock,
    ReceiverRejected,
    ReceiverSink,
    ReceiverTimeout,
    RejectReason,
    Tuning,
    UnsupportedAudioFormat,
    WaterfallRow,
)
from ghostjs8.receivers.directory import Directory
from ghostjs8.session.station import ReceiverTarget, Station, StationConfig
from ghostjs8.settings import Settings
from ghostjs8.store.sqlite import Store
from ghostjs8.util.backoff import Backoff
from ghostjs8.util.clock import ManualClock

# ------------------------------------------------------------------ fakes


class FakeDecoder:
    def __init__(self, sink: DecoderSink) -> None:
        self.sink = sink
        self.audio: list[bytes] = []
        self.connected = True

    def submit_audio(self, pcm_s16le: bytes) -> None:
        self.audio.append(pcm_s16le)

    async def run(self) -> None:
        await asyncio.Event().wait()

    async def close(self) -> None:
        pass


class FakeReceiver:
    """Scripted receiver: raises `fail` immediately, or runs until closed."""

    instances: ClassVar[list[FakeReceiver]] = []
    fail: ClassVar[Exception | None] = None

    def __init__(self, target: ReceiverTarget, tuning: Tuning, sink: ReceiverSink) -> None:
        self.target, self.tuning, self.sink = target, tuning, sink
        self.closed = asyncio.Event()
        self.retunes: list[Tuning] = []
        FakeReceiver.instances.append(self)

    async def run(self) -> None:
        if FakeReceiver.fail is not None:
            raise FakeReceiver.fail
        await self.closed.wait()

    async def close(self) -> None:
        self.closed.set()

    async def retune(self, tuning: Tuning) -> None:
        self.retunes.append(tuning)
        self.tuning = tuning


@pytest.fixture(autouse=True)
def reset_fakes() -> None:
    FakeReceiver.instances = []
    FakeReceiver.fail = None


def fast_backoff() -> Backoff:
    return Backoff(minimum_s=0.01, maximum_s=0.02, jitter=0.0)


def station(clock: ManualClock | None = None, **kw: object) -> Station:
    opts: dict[str, object] = {
        "receiver_backoff": fast_backoff(),
        "clock": clock or ManualClock(),
        # The 5 s politeness floor between connects has its own tests below.
        "config": StationConfig(min_connect_interval_s=0),
    }
    opts.update(kw)
    return Station(Hub(), FakeDecoder, FakeReceiver, **opts)  # type: ignore[arg-type]


EVENT = DecodeEvent(
    kind="activity",
    utc=datetime(2026, 10, 8, tzinfo=UTC),
    text="K0OG: KN4CRD SNR +02",
    snr_db=-22,
    offset_hz=705,
    speed="normal",
    from_call="K0OG",
)


def drain(q: asyncio.Queue[str | bytes]) -> list[object]:
    out: list[object] = []
    while not q.empty():
        item = q.get_nowait()
        out.append(item if isinstance(item, bytes) else server_message_adapter.validate_json(item))
    return out


async def wait_for(cond: object, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not cond():  # type: ignore[operator]
            await asyncio.sleep(0.005)


# ------------------------------------------------------------------- units


def test_backoff_grows_caps_and_resets() -> None:
    b = Backoff(minimum_s=5, maximum_s=300, jitter=0.0)
    delays = [b.next_delay() for _ in range(10)]
    assert delays[:4] == [5, 10, 20, 40]
    assert max(delays) == 300
    b.reset()
    assert b.next_delay() == 5


def test_backoff_jitter_stays_in_bounds() -> None:
    for r in (0.0, 1.0):
        b = Backoff(minimum_s=5, maximum_s=300, jitter=0.25, rand=lambda r=r: r)
        assert all(5 <= b.next_delay() <= 300 for _ in range(12))


async def test_hub_limits_subscriptions_and_drops_oldest() -> None:
    hub = Hub(max_clients=2, queue_size=2)
    a, b = hub.add(), hub.add()
    with pytest.raises(HubFull):
        hub.add()
    a.audio = True
    assert hub.wants("audio")
    assert not hub.wants("waterfall")
    hub.broadcast_binary("audio", b"x")
    assert a.queue.qsize() == 1
    assert b.queue.qsize() == 0
    for i in range(3):
        hub.broadcast_raw(f"m{i}")
    assert a.dropped == 2
    hub.remove(a)
    assert a.closed.is_set()


@pytest.mark.parametrize(
    ("host", "private", "ok"),
    [
        ("kiwi.example.org", False, True),
        ("1.1.1.1", False, True),
        ("192.168.1.20", True, True),
        ("192.168.1.20", False, False),
        ("127.0.0.1", True, False),
        ("::1", True, False),
        ("169.254.169.254", True, False),
        ("0.0.0.0", True, False),  # noqa: S104
        ("localhost", True, False),
        ("decoder", True, False),
        ("bad host!", True, False),
        ("x.localhost", True, False),
    ],
)
def test_receiver_host_validation(host: str, private: bool, ok: bool) -> None:
    if ok:
        assert validate_receiver_host(host, allow_private=private)
    else:
        with pytest.raises(InvalidReceiver):
            validate_receiver_host(host, allow_private=private)


def test_rate_limiter() -> None:
    clock = ManualClock()
    rl = RateLimiter(clock, burst=2, window_s=5)
    assert rl.allow()
    assert rl.allow()
    assert not rl.allow()
    clock.advance(5)
    assert rl.allow()


def test_settings_from_env() -> None:
    s = Settings.from_env(
        {
            "GHOSTJS8_RECEIVER_HOST": "kiwi.example",
            "GHOSTJS8_DIAL_HZ": "7078000",
            "GHOSTJS8_MODE": "LSB",
            "GHOSTJS8_ALLOWED_ORIGINS": "https://a, https://b",
            "GHOSTJS8_ALLOW_PRIVATE_RECEIVERS": "false",
            "GHOSTJS8_IDLE_DISCONNECT_MINUTES": "5",
        }
    )
    assert s.receiver_host == "kiwi.example"
    assert s.tuning == Tuning(dial_hz=7_078_000, mode="lsb")
    assert s.allowed_origins == ("https://a", "https://b")
    assert not s.allow_private_receivers
    assert s.idle_disconnect_minutes == 5
    with pytest.raises(ValueError, match="usb or lsb"):
        Settings.from_env({"GHOSTJS8_MODE": "am"})


def test_binary_frame_layouts() -> None:
    a = binary.encode_audio(7, 12000, b"\x01\x00\x02\x00", adc_overload=True)
    assert struct.unpack_from("<BBHII", a) == (1, 1, 0, 7, 12000)
    assert a[12:] == b"\x01\x00\x02\x00"
    w = binary.encode_waterfall(9, 14_000_000, 12_000, bytes(1024))
    assert struct.unpack_from("<BBHIII", w) == (2, 0, 1024, 9, 14_000_000, 12_000)
    assert len(w) == 16 + 1024


# --------------------------------------------------------- station: data path


async def test_audio_routes_to_decoder_and_only_subscribed_clients() -> None:
    st = station()
    sub, other = st.hub.add(), st.hub.add()
    sub.audio = True
    st.on_audio(AudioBlock(seq=3, pcm_s16le=b"\x00\x01", rssi_dbm=-60, adc_overload=False))
    assert isinstance(st.decoder, FakeDecoder)
    assert st.decoder.audio == [b"\x00\x01"]
    assert st.state == "connected"
    frames = [x for x in drain(sub.queue) if isinstance(x, bytes)]
    assert frames == [binary.encode_audio(3, 12000, b"\x00\x01", adc_overload=False)]
    assert not [x for x in drain(other.queue) if isinstance(x, bytes)]


async def test_waterfall_frame_rate_cap() -> None:
    clock = ManualClock()
    st = station(clock, config=StationConfig(waterfall_max_fps=10, min_connect_interval_s=0))
    c = st.hub.add()
    c.waterfall = True
    row = WaterfallRow(seq=1, start_hz=0, span_hz=12_000, bins=bytes(1024))
    for _ in range(5):  # 5 rows within 50 ms: only the first passes
        st.on_waterfall(row)
        clock.advance(0.01)
    clock.advance(0.1)
    st.on_waterfall(row)
    assert len([x for x in drain(c.queue) if isinstance(x, bytes)]) == 2


async def test_adc_overload_status_debounced() -> None:
    clock = ManualClock()
    st = station(clock)
    c = st.hub.add()
    st.on_audio(AudioBlock(seq=1, pcm_s16le=b"", rssi_dbm=-30, adc_overload=True))
    msgs = [m for m in drain(c.queue) if isinstance(m, ReceiverStatus)]
    assert msgs[-1].adc_overload
    clock.advance(1.0)
    st.on_audio(AudioBlock(seq=2, pcm_s16le=b"", rssi_dbm=-30, adc_overload=False))
    assert st.receiver_status().adc_overload  # held for 2 s, no flapping
    clock.advance(1.5)
    st.on_audio(AudioBlock(seq=3, pcm_s16le=b"", rssi_dbm=-30, adc_overload=False))
    msgs = [m for m in drain(c.queue) if isinstance(m, ReceiverStatus)]
    assert not msgs[-1].adc_overload


async def test_decode_is_stored_broadcast_and_station_counted_once() -> None:
    clock = ManualClock()
    store = Store(":memory:", clock)
    st = station(clock, store=store)
    c = st.hub.add()
    st.on_decode(EVENT)
    directed = replace(EVENT, kind="directed", grid="EN34")
    st.on_decode(directed)
    st.on_decode(replace(EVENT, from_call="@ALLCALL"))
    msgs = drain(c.queue)
    decodes = [m for m in msgs if isinstance(m, Decode)]
    stations = [m for m in msgs if isinstance(m, StationMsg)]
    assert [d.freq_hz for d in decodes] == [14_078_705] * 3
    assert [s.callsign for s in stations] == ["K0OG", "K0OG"]  # groups are not stations
    assert stations[-1].grid == "EN34"
    assert stations[-1].heard_count == 1
    assert len(store.recent_decodes()) == 3
    assert st.health.snapshot().last_decode_utc == EVENT.utc


async def test_spots_never_map_invalid_grids() -> None:
    st = station()
    c = st.hub.add()
    st.on_spot(SpotEvent("KG9B", EVENT.utc, -15, None, "XX99zz"))
    st.on_spot(SpotEvent("K0OG", EVENT.utc, -22, None, "en34"))
    stations = [m for m in drain(c.queue) if isinstance(m, StationMsg)]
    assert [(s.callsign, s.grid) for s in stations] == [("KG9B", None), ("K0OG", "EN34")]


async def test_client_join_sends_hello_history_session_health_status() -> None:
    clock = ManualClock()
    store = Store(":memory:", clock)
    st = station(clock, store=store)
    st.on_decode(EVENT)
    c = st.hub.add()
    st.client_joined(c)
    kinds = [type(m) for m in drain(c.queue)]
    assert kinds[:5] == [Hello, History, Session, Health, ReceiverStatus]


# ------------------------------------------------------- station: lifecycle


async def run_station(st: Station) -> asyncio.Task[None]:
    task = asyncio.create_task(st.run())
    await asyncio.sleep(0)
    return task


async def test_select_tune_and_disconnect() -> None:
    st = station()
    task = await run_station(st)
    try:
        st.select_receiver(ReceiverTarget("kiwi.example", 8073))
        await wait_for(lambda: len(FakeReceiver.instances) == 1)
        assert st.state == "connecting"
        rx = FakeReceiver.instances[0]
        await st.tune(Tuning(dial_hz=7_078_000, mode="lsb"))
        assert rx.retunes == [Tuning(dial_hz=7_078_000, mode="lsb")]
        st.select_receiver(ReceiverTarget("other.example", 8073))
        await wait_for(lambda: len(FakeReceiver.instances) == 2)
        assert rx.closed.is_set()
        assert FakeReceiver.instances[1].tuning.dial_hz == 7_078_000
        st.disconnect_receiver()
        await wait_for(lambda: st.state == "idle")
    finally:
        task.cancel()


@pytest.mark.parametrize(
    ("exc", "state", "retries"),
    [
        (ReceiverRejected(RejectReason.AUTH), "rejected", False),
        (ReceiverRejected(RejectReason.REDIRECT, "x"), "rejected", False),
        (UnsupportedAudioFormat("compressed"), "failed", False),
        (ReceiverTimeout("slow"), "backoff", True),
    ],
)
async def test_failure_policy(exc: Exception, state: str, retries: bool) -> None:
    FakeReceiver.fail = exc
    st = station()
    task = await run_station(st)
    try:
        st.select_receiver(ReceiverTarget("kiwi.example", 8073))
        await wait_for(lambda: st.state == state)
        await asyncio.sleep(0.1)
        assert (len(FakeReceiver.instances) > 1) is retries
    finally:
        task.cancel()


async def test_full_receiver_waits_patiently() -> None:
    FakeReceiver.fail = ReceiverRejected(RejectReason.FULL, "all 4 slots taken")
    st = station()
    task = await run_station(st)
    try:
        st.select_receiver(ReceiverTarget("kiwi.example", 8073))
        await wait_for(lambda: st.next_retry_utc is not None)
        assert st.reject_reason == "full"
        assert st.next_retry_utc is not None
        assert (st.next_retry_utc - st.clock.utc_now()).total_seconds() >= 60
        assert len(FakeReceiver.instances) == 1
    finally:
        task.cancel()


async def test_idle_disconnect_and_resume() -> None:
    clock = ManualClock()
    st = station(
        clock,
        target=ReceiverTarget("kiwi.example", 8073),
        config=StationConfig(idle_disconnect_s=60, min_connect_interval_s=0),
    )
    task = await run_station(st)
    try:
        await wait_for(lambda: len(FakeReceiver.instances) == 1)
        clock.advance(61)
        await wait_for(lambda: st.state == "idle", timeout=3)
        assert FakeReceiver.instances[0].closed.is_set()
        st.client_joined(st.hub.add())
        await wait_for(lambda: len(FakeReceiver.instances) == 2)
    finally:
        task.cancel()


# -------------------------------------------------------------------- HTTP/WS


def app_with(st: Station, **kw: object) -> TestClient:
    settings = Settings(db_path="", **kw)  # type: ignore[arg-type]

    async def fetch(url: str) -> bytes:
        return (
            b'var x = [{"id":"a","status":"active","offline":"no","url":"http://192.0.2.1:8073"},];'
        )

    return TestClient(create_app(st, settings, directory=Directory(fetch=fetch)))


def test_ws_handshake_messages_and_cleanup() -> None:
    st = station()
    with app_with(st) as http, http.websocket_connect("/ws") as ws:
        first = server_message_adapter.validate_json(ws.receive_text())
        assert isinstance(first, Hello)
        assert first.receive_only is True
        assert st.hub.client_count == 1
    assert st.hub.client_count == 0


def test_ws_control_messages() -> None:
    st = station()
    select_loopback = {
        "v": 1,
        "type": "select_receiver",
        "receiver": {"host": "127.0.0.1", "port": 8073, "name": None},
        "password": "",
    }
    with app_with(st) as http, http.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"v": 1, "type": "ping"}))
        ws.send_text("not json")
        ws.send_text(json.dumps({"v": 2, "type": "ping"}))
        ws.send_text(json.dumps({"v": 1, "type": "transmit", "text": "CQ"}))
        ws.send_text(json.dumps(select_loopback))
        seen: list[object] = []
        while len([m for m in seen if isinstance(m, Error)]) < 4:
            seen.append(server_message_adapter.validate_json(ws.receive_text()))
        codes = [m.code for m in seen if isinstance(m, Error)]
        assert codes == ["bad_message", "unsupported_version", "bad_message", "invalid_receiver"]
        assert any(type(m).__name__ == "Pong" for m in seen)


def test_ws_origin_allowlist() -> None:
    st = station()
    with app_with(st, allowed_origins=("https://ghost.example",)) as http:
        with (
            pytest.raises(WebSocketDisconnect),
            http.websocket_connect("/ws", headers={"origin": "https://evil"}),
        ):
            pass
        with http.websocket_connect("/ws", headers={"origin": "https://ghost.example"}) as ws:
            assert json.loads(ws.receive_text())["type"] == "hello"


def test_ws_session_full() -> None:
    st = Station(Hub(max_clients=1), FakeDecoder, FakeReceiver)  # type: ignore[arg-type]
    with app_with(st) as http, http.websocket_connect("/ws") as ws1:
        ws1.receive_text()
        with pytest.raises(WebSocketDisconnect), http.websocket_connect("/ws"):
            pass


def test_http_endpoints() -> None:
    st = station()
    with app_with(st) as http:
        assert http.get("/healthz").json() == {"status": "ok"}
        ready = http.get("/readyz")
        assert ready.status_code == 503  # nothing connected: not ready, and says why
        assert Health.model_validate(ready.json()).overall == "offline"
        directory = ReceiverDirectory.model_validate(http.get("/api/receivers").json())
        assert [r.host for r in directory.receivers] == ["192.0.2.1"]

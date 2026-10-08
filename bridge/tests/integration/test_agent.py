"""decoder-agent pieces over real localhost sockets (no container)."""

from __future__ import annotations

import asyncio
import json
import socket
import sys
from datetime import UTC, datetime

import pytest

from ghostjs8.decoders.base import DecodeEvent, DecoderHealth, DecoderUnavailable, SpotEvent
from ghostjs8.decoders.js8call_native import agent_protocol as proto
from ghostjs8.decoders.js8call_native.adapter import Js8CallNativeDecoder
from ghostjs8.decoders.js8call_native.agent import (
    Agent,
    Js8UdpApi,
    PcmSink,
    js8call_capturing,
    parse_supervisor_status,
)
from ghostjs8.util.clock import ManualClock


async def udp_api() -> tuple[Js8UdpApi, asyncio.Queue[str], int, asyncio.DatagramTransport]:
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=8)
    api = Js8UdpApi(ManualClock(), q)
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(lambda: api, local_addr=("127.0.0.1", 0))
    port = transport.get_extra_info("sockname")[1]
    return api, q, port, transport


def js8_socket() -> socket.socket:
    """Plays JS8Call: sends from an ephemeral port and listens there for replies."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    s.settimeout(2)
    return s


async def test_reply_port_learned_and_requests_reach_it() -> None:
    api, _, port, transport = await udp_api()
    js8 = js8_socket()
    try:
        assert api.request("RX.GET_CALL_ACTIVITY") is False  # nowhere to send yet
        js8.sendto(
            json.dumps({"type": "PING", "value": "", "params": {}}).encode(), ("127.0.0.1", port)
        )
        await asyncio.sleep(0.05)
        assert api.reply_addr == js8.getsockname()
        assert api.last_ping is not None
        assert api.request("RX.GET_CALL_ACTIVITY") is True
        data = await asyncio.to_thread(js8.recv, 4096)
        req = json.loads(data)
        assert req["type"] == "RX.GET_CALL_ACTIVITY"
        # the reply carries our _ID -> round trip recorded
        assert api.last_reply is None
        reply = {"type": "RX.CALL_ACTIVITY", "value": "", "params": {"_ID": req["params"]["_ID"]}}
        js8.sendto(json.dumps(reply).encode(), ("127.0.0.1", port))
        await asyncio.sleep(0.05)
        assert api.last_reply is not None
    finally:
        js8.close()
        transport.close()


async def test_forwards_decodes_and_ignores_noise() -> None:
    _api, q, port, transport = await udp_api()
    js8 = js8_socket()
    try:
        for msg in (
            {"type": "STATION.STATUS", "value": "", "params": {}},
            {"type": "RX.ACTIVITY", "value": "A: B", "params": {"SNR": 1, "OFFSET": 2}},
            {"type": "RX.DIRECTED", "value": "B ♢", "params": {"FROM": "A", "SNR": 1, "OFFSET": 2}},
            {"type": "SOMETHING.NEW", "value": "", "params": {}},
        ):
            js8.sendto(json.dumps(msg).encode(), ("127.0.0.1", port))
        js8.sendto(b"\xff not json", ("127.0.0.1", port))
        await asyncio.sleep(0.1)
        types = [json.loads(q.get_nowait())["msg"]["type"] for _ in range(q.qsize())]
        assert types == ["RX.ACTIVITY", "RX.DIRECTED"]
    finally:
        js8.close()
        transport.close()


async def test_transmit_requests_are_impossible() -> None:
    api, _, _, transport = await udp_api()
    try:
        for bad in ("TX.SEND_MESSAGE", "TX.SET_TEXT", "STATION.SET_CALLSIGN", "RIG.SET_FREQ"):
            with pytest.raises(ValueError, match="not allowed"):
                api.request(bad)
    finally:
        transport.close()


def test_supervisor_status_parsing() -> None:
    out = "js8call                          RUNNING   pid 11, uptime 0:00:24\n"
    assert parse_supervisor_status(out, "js8call")
    assert not parse_supervisor_status("js8call   BACKOFF   Exited too quickly\n", "js8call")
    assert not parse_supervisor_status("", "js8call")


SOURCES = json.dumps(
    [{"index": 0, "name": "ghost_rx.monitor"}, {"index": 1, "name": "ghost_rx_in"}]
)


def outputs(source: int, binary: str, corked: bool) -> str:
    return json.dumps(
        [
            {
                "index": 1,
                "source": source,
                "corked": corked,
                "properties": {"application.process.binary": binary},
            }
        ]
    )


@pytest.mark.parametrize(
    ("outs", "expected"),
    [
        (outputs(1, "JS8Call", False), True),
        (outputs(1, "JS8Call", True), False),  # corked: not capturing
        (outputs(0, "JS8Call", False), False),  # wrong source
        (outputs(1, "pacat", False), False),  # someone else
        ("not json", False),
    ],
)
def test_capture_detection(outs: str, expected: bool) -> None:
    assert js8call_capturing(SOURCES, outs) is expected


async def test_pcm_sink_is_bounded_and_drops_oldest() -> None:
    sink = PcmSink(ManualClock(), command=("cat",), max_blocks=3)
    for i in range(5):
        sink.submit(bytes([i]))
    assert sink.dropped == 2
    assert [sink.queue.get_nowait() for _ in range(3)] == [b"\x02", b"\x03", b"\x04"]


async def test_pcm_sink_writes_through_process() -> None:
    sink = PcmSink(
        ManualClock(), command=(sys.executable, "-c", "import sys; sys.stdin.buffer.read()")
    )
    task = asyncio.create_task(sink.run())
    sink.submit(b"\x00\x01" * 256)
    async with asyncio.timeout(5):
        while sink.last_write is None:
            await asyncio.sleep(0.02)
    task.cancel()
    # Let run() kill and reap the child inside this loop (no transport GC after close).
    await asyncio.gather(task, return_exceptions=True)


# --------------------------------------------------- agent <-> bridge adapter


class Collect:
    def __init__(self) -> None:
        self.decodes: list[DecodeEvent] = []
        self.spots: list[SpotEvent] = []
        self.health: list[DecoderHealth] = []

    def on_decode(self, event: DecodeEvent) -> None:
        self.decodes.append(event)

    def on_spot(self, event: SpotEvent) -> None:
        self.spots.append(event)

    def on_health(self, health: DecoderHealth) -> None:
        self.health.append(health)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def test_agent_end_to_end_with_bridge_adapter() -> None:
    async def probe() -> tuple[bool, bool]:
        return True, True

    written: list[bytes] = []
    pcm = PcmSink(
        ManualClock(), command=(sys.executable, "-c", "import sys; sys.stdin.buffer.read()")
    )
    agent = Agent(
        udp_port=0, pcm=pcm, probe=probe, health_interval_s=0.05, call_activity_interval_s=60
    )
    ws_port = free_port()
    agent_task = asyncio.create_task(agent.serve("127.0.0.1", ws_port))
    await asyncio.sleep(0.2)
    udp_port = agent.udp._transport.get_extra_info("sockname")[1]  # type: ignore[union-attr]

    sink = Collect()
    dec = Js8CallNativeDecoder(f"ws://127.0.0.1:{ws_port}/agent", sink)
    dec_task = asyncio.create_task(dec.run())
    try:
        async with asyncio.timeout(5):
            while not (dec.connected and sink.health):
                await asyncio.sleep(0.02)
        assert sink.health[-1].process_up
        assert sink.health[-1].capturing

        dec.submit_audio(b"\x01\x00" * 512)
        async with asyncio.timeout(5):
            while pcm.last_write is None:
                await asyncio.sleep(0.02)
        written.append(b"ok")

        js8 = js8_socket()
        js8.sendto(json.dumps(DIRECTED).encode(), ("127.0.0.1", udp_port))
        async with asyncio.timeout(5):
            while not sink.decodes:
                await asyncio.sleep(0.02)
        js8.close()
        assert sink.decodes[0].text == "K0OG: KN4CRD SNR +02"
    finally:
        dec_task.cancel()
        agent_task.cancel()
        await asyncio.gather(dec_task, agent_task, return_exceptions=True)


async def test_adapter_raises_unavailable_when_agent_down() -> None:
    dec = Js8CallNativeDecoder(
        f"ws://127.0.0.1:{free_port()}/agent", Collect(), connect_timeout_s=1
    )
    with pytest.raises(DecoderUnavailable):
        await dec.run()


def test_adapter_drops_oldest_audio_when_offline() -> None:
    dec = Js8CallNativeDecoder("ws://unused/agent", Collect(), max_pending_blocks=2)
    for i in range(4):
        dec.submit_audio(bytes([i]))
    assert dec.dropped_audio_blocks == 2


def test_health_roundtrip() -> None:
    t = datetime(2026, 10, 8, tzinfo=UTC)
    h = DecoderHealth(True, False, t, None, t, 3, {"udp_reply_port": "4242"})
    assert proto.decode_health(json.loads(proto.encode_health(h, t))) == h


DIRECTED = {
    "type": "RX.DIRECTED",
    "value": "KN4CRD SNR +02 ♢ ",
    "params": {
        "FROM": "K0OG",
        "TO": "KN4CRD",
        "SNR": -22,
        "OFFSET": 705,
        "SPEED": 0,
        "UTC": 1791424811558,
    },
}

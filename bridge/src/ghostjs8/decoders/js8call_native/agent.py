"""decoder-agent: runs inside the decoder container next to JS8Call.

- Accepts one bridge WebSocket (``/agent``); a newer connection replaces an older one.
- Writes incoming PCM into the PulseAudio null sink ``ghost_rx`` through ``pacat``
  with a bounded queue (drop, never grow latency).
- Owns JS8Call's UDP API on localhost: learns the reply port from incoming
  datagrams, forwards decode/station messages, and polls call activity.
- Reports health facts: JS8Call process state, whether JS8Call holds an uncorked
  capture stream on ``ghost_rx_in``, API heartbeat (PING) and request/reply
  round trips, and when audio was last written.

Run: ``python -m ghostjs8.decoders.js8call_native.agent``
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import itertools
import json
import logging
import os
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from ghostjs8.decoders.base import DecoderHealth
from ghostjs8.decoders.js8call_native import agent_protocol as proto
from ghostjs8.decoders.js8call_native.messages import FORWARDED_TYPES
from ghostjs8.decoders.js8call_native.selftest import (
    Action,
    CanaryMixer,
    SelfTest,
    load_clip,
)
from ghostjs8.util.clock import Clock, SystemClock
from ghostjs8.util.logs import configure

log = logging.getLogger("ghostjs8.agent")

# Read-only requests the agent may send to JS8Call. Nothing else, ever: in
# particular no TX.* type can be constructed by this module.
ALLOWED_REQUESTS = frozenset({"RX.GET_CALL_ACTIVITY", "STATION.GET_CALLSIGN"})

PACAT_CMD = (
    "pacat",
    "--playback",
    "--device=ghost_rx",
    "--raw",
    "--format=s16le",
    "--rate=12000",
    "--channels=1",
    "--latency-msec=200",
    "--client-name=ghost-agent",
    "--stream-name=receiver",
)


# --------------------------------------------------------------------- UDP API


class Js8UdpApi(asyncio.DatagramProtocol):
    """JS8Call's UDP API endpoint on localhost."""

    def __init__(
        self,
        clock: Clock,
        forward: asyncio.Queue[str],
        selftest: SelfTest | None = None,
    ) -> None:
        self._clock = clock
        self._forward = forward
        self._selftest = selftest
        self._transport: asyncio.DatagramTransport | None = None
        self.reply_addr: tuple[str, int] | None = None
        self.last_ping: datetime | None = None
        self.last_reply: datetime | None = None
        self._pending: set[int] = set()
        self._ids = itertools.count(1)
        self.dropped_forwards = 0

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        if isinstance(transport, asyncio.DatagramTransport):
            self._transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        # Learn where JS8Call listens for replies: the source of its datagrams.
        self.reply_addr = (str(addr[0]), int(addr[1]))
        try:
            message = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            log.warning("ignoring non-JSON datagram from %s", addr)
            return
        if not isinstance(message, dict):
            return
        mtype = message.get("type")
        now = self._clock.utc_now()
        if mtype == "PING":
            self.last_ping = now
        params = message.get("params")
        msg_id = params.get("_ID") if isinstance(params, dict) else None
        if isinstance(msg_id, int) and msg_id in self._pending:
            self._pending.discard(msg_id)
            self.last_reply = now
        if self._selftest is not None and self._selftest.intercept(message, now):
            return  # the decoder's answer to our own self-test frame: never forwarded
        if mtype in FORWARDED_TYPES:
            try:
                self._forward.put_nowait(proto.encode_js8(message, now))
            except asyncio.QueueFull:
                self.dropped_forwards += 1

    def request(self, mtype: str) -> bool:
        """Send a read-only request to JS8Call. False if we do not know where yet."""
        if mtype not in ALLOWED_REQUESTS:
            raise ValueError(f"request type not allowed: {mtype}")
        if self._transport is None or self.reply_addr is None:
            return False
        msg_id = next(self._ids)
        self._pending.add(msg_id)
        if len(self._pending) > 32:  # replies lost; do not grow without bound
            self._pending = {msg_id}
        payload = {"type": mtype, "value": "", "params": {"_ID": msg_id}}
        self._transport.sendto(json.dumps(payload).encode(), self.reply_addr)
        return True


# ------------------------------------------------------------------- PCM sink


@dataclass
class PcmSink:
    """Bounded PCM pipe into PulseAudio via a long-running pacat process."""

    clock: Clock
    command: Sequence[str] = PACAT_CMD
    max_blocks: int = 48  # ~2 s of 512-sample blocks
    queue: asyncio.Queue[bytes] = field(init=False)
    last_write: datetime | None = None
    dropped: int = 0

    def __post_init__(self) -> None:
        self.queue = asyncio.Queue(maxsize=self.max_blocks)

    def submit(self, pcm: bytes) -> None:
        if self.queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()  # drop oldest: keep latency bounded
            self.dropped += 1
        self.queue.put_nowait(pcm)

    async def run(self) -> None:
        while True:
            proc = await asyncio.create_subprocess_exec(
                *self.command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL
            )
            log.info("pcm writer started (pid %s)", proc.pid)
            try:
                await self._pump(proc)
            except (BrokenPipeError, ConnectionResetError) as exc:
                log.warning("pcm writer pipe broke: %s", exc)
            finally:
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
            log.warning("pcm writer exited (%s); restarting", proc.returncode)
            await asyncio.sleep(1.0)

    async def _pump(self, proc: asyncio.subprocess.Process) -> None:
        if proc.stdin is None:  # pragma: no cover - PIPE always set
            return
        while proc.returncode is None:
            pcm = await self.queue.get()
            proc.stdin.write(pcm)
            await proc.stdin.drain()
            self.last_write = self.clock.utc_now()


# ---------------------------------------------------------------- health probes


def parse_supervisor_status(output: str, program: str) -> bool:
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == program:
            return parts[1] == "RUNNING"
    return False


def js8call_capturing(
    sources_json: str, outputs_json: str, source_name: str = "ghost_rx_in"
) -> bool:
    """True if JS8Call holds an uncorked capture stream on the given source."""
    try:
        sources = json.loads(sources_json)
        outputs = json.loads(outputs_json)
    except json.JSONDecodeError:
        return False
    indices = {
        s.get("index") for s in sources if isinstance(s, dict) and s.get("name") == source_name
    }
    if not indices:
        return False
    for out in outputs:
        if not isinstance(out, dict):
            continue
        props = out.get("properties")
        binary = props.get("application.process.binary") if isinstance(props, dict) else None
        if out.get("source") in indices and binary == "JS8Call" and out.get("corked") is False:
            return True
    return False


async def _run(*cmd: str, timeout_s: float = 4) -> str:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout_s)
    except TimeoutError:
        proc.kill()
        return ""
    return out.decode(errors="replace")


async def probe_container() -> tuple[bool, bool]:
    status = await _run(
        "supervisorctl", "-c", "/etc/ghostjs8/supervisord.conf", "status", "js8call"
    )
    sources = await _run("pactl", "-f", "json", "list", "short", "sources")
    outputs = await _run("pactl", "-f", "json", "list", "source-outputs")
    return parse_supervisor_status(status, "js8call"), js8call_capturing(sources, outputs)


# ---------------------------------------------------------------------- agent

Probe = Callable[[], Awaitable[tuple[bool, bool]]]
Restart = Callable[[], Awaitable[None]]

SUPERVISORCTL = ("supervisorctl", "-c", "/etc/ghostjs8/supervisord.conf")
SELFTEST_AUDIO_FRESH_S = 3.0  # audio must be flowing for a test to mean anything
DEFAULT_CLIP = "/usr/share/ghostjs8/selftest/canary-js8-normal.wav"


async def restart_js8call() -> None:
    await _run(*SUPERVISORCTL, "restart", "js8call", timeout_s=30)


class Agent:
    def __init__(
        self,
        *,
        clock: Clock | None = None,
        udp_host: str = "127.0.0.1",
        udp_port: int = 2242,
        pcm: PcmSink | None = None,
        probe: Probe = probe_container,
        health_interval_s: float = 3.0,
        call_activity_interval_s: float = 15.0,
        selftest: SelfTest | None = None,
        restart: Restart = restart_js8call,
    ) -> None:
        self.clock = clock or SystemClock()
        self.forward: asyncio.Queue[str] = asyncio.Queue(maxsize=512)
        self.selftest = selftest
        self.udp = Js8UdpApi(self.clock, self.forward, selftest)
        self.pcm = pcm or PcmSink(self.clock)
        self._probe = probe
        self._restart = restart
        self.selftest_hold = False
        self._udp_addr = (udp_host, udp_port)
        self._health_interval_s = health_interval_s
        self._call_activity_interval_s = call_activity_interval_s
        self._bridge: ServerConnection | None = None
        self.health = DecoderHealth(False, False, None, None, None)

    async def serve(self, host: str, port: int) -> None:
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: self.udp, local_addr=self._udp_addr
        )
        try:
            async with (
                serve(self._handle, host, port, compression=None, max_size=2**20),
                asyncio.TaskGroup() as tg,
            ):
                log.info(
                    "agent listening ws://%s:%d%s, udp %s:%d",
                    host,
                    port,
                    proto.AGENT_PATH,
                    *self._udp_addr,
                )
                tg.create_task(self.pcm.run())
                tg.create_task(self._health_loop())
                tg.create_task(self._call_activity_loop())
                tg.create_task(self._forward_loop())
                tg.create_task(self._selftest_loop())
        finally:
            transport.close()

    async def _handle(self, ws: ServerConnection) -> None:
        if ws.request is None or ws.request.path != proto.AGENT_PATH:
            await ws.close(1008, "unknown path")
            return
        if self._bridge is not None:
            await self._bridge.close(1000, "replaced by a newer bridge connection")
        self._bridge = ws
        log.info("bridge connected from %s", ws.remote_address)
        try:
            await ws.send(proto.encode_health(self.health, self.clock.utc_now()))
            async for message in ws:
                if isinstance(message, bytes):
                    self.pcm.submit(self._mix(message))
                else:
                    self._control(message)
        except ConnectionClosed:
            pass
        finally:
            if self._bridge is ws:
                self._bridge = None
            log.info("bridge disconnected")

    def _mix(self, pcm: bytes) -> bytes:
        return pcm if self.selftest is None else self.selftest.mix(pcm, self.clock.utc_now())

    def _control(self, text: str) -> None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return
        if isinstance(payload, dict) and payload.get("t") == "selftest_hold":
            self.selftest_hold = payload.get("hold") is True

    async def _send(self, text: str) -> None:
        ws = self._bridge
        if ws is None:
            return
        with contextlib.suppress(ConnectionClosed):
            await ws.send(text)

    async def _forward_loop(self) -> None:
        while True:
            await self._send(await self.forward.get())

    async def _health_loop(self) -> None:
        while True:
            process_up, capturing = await self._probe()
            self.health = DecoderHealth(
                process_up=process_up,
                capturing=capturing,
                last_ping_utc=self.udp.last_ping,
                last_api_reply_utc=self.udp.last_reply,
                last_audio_write_utc=self.pcm.last_write,
                dropped_audio_blocks=self.pcm.dropped,
                details={
                    "udp_reply_port": str(self.udp.reply_addr[1]) if self.udp.reply_addr else ""
                },
                selftest=self.selftest.facts() if self.selftest else None,
            )
            await self._send(proto.encode_health(self.health, self.clock.utc_now()))
            await asyncio.sleep(self._health_interval_s)

    def _selftest_ready(self) -> bool:
        """A test only means something with a bridge feeding audio and JS8Call listening."""
        last = self.pcm.last_write
        fresh = (
            self._bridge is not None
            and last is not None
            and (self.clock.utc_now() - last).total_seconds() <= SELFTEST_AUDIO_FRESH_S
        )
        return fresh and self.health.process_up and self.health.capturing

    async def _selftest_loop(self) -> None:
        if self.selftest is None:
            return
        while True:
            await asyncio.sleep(1.0)
            action = self.selftest.step(ready=self._selftest_ready(), hold=self.selftest_hold)
            if action is Action.RESTART_DECODER:
                log.warning("self-test: restarting JS8Call")
                await self._restart()

    async def _call_activity_loop(self) -> None:
        while True:
            await asyncio.sleep(self._call_activity_interval_s)
            self.udp.request("RX.GET_CALL_ACTIVITY")


def selftest_from_env(clock: Clock | None = None) -> SelfTest | None:
    """The self-test, unless disabled or its clip is unusable (logged; the agent still runs)."""
    if os.environ.get("GHOSTJS8_SELFTEST", "on").strip().lower() in ("off", "0", "false", "no"):
        log.info("self-test disabled (GHOSTJS8_SELFTEST=off)")
        return None
    clip = os.environ.get("GHOSTJS8_SELFTEST_CLIP", DEFAULT_CLIP)
    try:
        mixer = CanaryMixer(load_clip(clip))
    except ValueError:
        log.exception("self-test unavailable")
        return None
    interval = float(os.environ.get("GHOSTJS8_SELFTEST_INTERVAL_S", "3600"))
    first = float(os.environ.get("GHOSTJS8_SELFTEST_FIRST_DELAY_S", "300"))
    return SelfTest(clock or SystemClock(), mixer, interval_s=interval, first_delay_s=first)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="ghost.js8 decoder-agent")
    p.add_argument("--host", default="0.0.0.0")  # noqa: S104 - internal container network
    p.add_argument("--port", type=int, default=proto.DEFAULT_AGENT_PORT)
    p.add_argument("--udp-port", type=int, default=2242)
    args = p.parse_args(argv)
    configure("decoder-agent")
    asyncio.run(
        Agent(udp_port=args.udp_port, selftest=selftest_from_env()).serve(args.host, args.port)
    )


if __name__ == "__main__":
    main()

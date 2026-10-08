"""HTTP + WebSocket API for browsers.

- ``GET /healthz``  liveness: the bridge process is serving
- ``GET /readyz``   readiness: full component health (200 when listening, 503 otherwise)
- ``GET /api/receivers``  cached public receiver directory
- ``WS  /ws``       the browser protocol (see contract/messages.py, docs/protocol.md)
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import re
from collections.abc import AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ghostjs8.api.hub import Client, HubFull
from ghostjs8.contract.messages import (
    ClientMessage,
    DisconnectReceiver,
    Error,
    ErrorCode,
    Ping,
    Pong,
    SelectReceiver,
    Subscribe,
    Tune,
    client_message_adapter,
)
from ghostjs8.receivers.base import Tuning
from ghostjs8.receivers.directory import Directory
from ghostjs8.session.station import ReceiverTarget, Station
from ghostjs8.settings import Settings
from ghostjs8.util.clock import Clock, SystemClock

log = logging.getLogger("ghostjs8.api")

CONTROL_BURST = 10  # control messages per client ...
CONTROL_WINDOW_S = 5.0  # ... per this many seconds
MAX_CLIENT_MESSAGE_BYTES = 4096
_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.?$"
)
_BLOCKED_NAMES = frozenset({"localhost", "decoder", "bridge", "web", "fake-kiwi"})


class InvalidReceiver(ValueError):
    pass


def validate_receiver_host(host: str, *, allow_private: bool) -> str:
    """Reject receiver addresses that would point the bridge at itself or its peers.

    Literal IPs are checked against loopback/link-local/multicast/unspecified,
    and private ranges unless allowed. Hostnames are syntax-checked; the
    container's own service names are refused.
    """
    h = host.strip().rstrip(".").lower()
    try:
        ip = ipaddress.ip_address(h.strip("[]"))
    except ValueError:
        if not _HOSTNAME.match(h) or h in _BLOCKED_NAMES or h.endswith(".localhost"):
            raise InvalidReceiver(f"not an allowed receiver host: {host!r}") from None
        return h
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        raise InvalidReceiver(f"not an allowed receiver address: {host!r}")
    if ip.is_private and not allow_private:
        raise InvalidReceiver(f"private receiver addresses are disabled: {host!r}")
    return str(ip)


class RateLimiter:
    def __init__(
        self, clock: Clock, burst: int = CONTROL_BURST, window_s: float = CONTROL_WINDOW_S
    ) -> None:
        self._clock, self._burst, self._window = clock, burst, window_s
        self._stamps: list[float] = []

    def allow(self) -> bool:
        now = self._clock.monotonic()
        self._stamps = [t for t in self._stamps if now - t < self._window]
        if len(self._stamps) >= self._burst:
            return False
        self._stamps.append(now)
        return True


def create_app(
    station: Station,
    settings: Settings,
    *,
    directory: Directory | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    clk = clock or SystemClock()
    receivers = directory or Directory(source=settings.directory_url)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(station.run(), name="station")
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="ghost.js8 bridge", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        snap = station.health.snapshot()
        return JSONResponse(
            json.loads(snap.model_dump_json()),
            status_code=200 if snap.overall == "listening" else 503,
        )

    @app.get("/api/receivers")
    async def api_receivers() -> JSONResponse:
        return JSONResponse(json.loads((await receivers.get()).model_dump_json()))

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        origin = ws.headers.get("origin")
        if settings.allowed_origins and origin not in settings.allowed_origins:
            await ws.close(code=1008, reason="origin not allowed")
            return
        try:
            client = station.hub.add()
        except HubFull:
            await ws.close(code=1013, reason="session full")
            return
        await ws.accept()
        limiter = RateLimiter(clk)
        try:
            station.client_joined(client)
            async with asyncio.TaskGroup() as tg:
                tg.create_task(_pump_out(ws, client.queue))
                tg.create_task(_pump_in(ws, client, station, settings, limiter))
        except* (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            station.hub.remove(client)
            station.client_left()

    return app


async def _pump_out(ws: WebSocket, queue: asyncio.Queue[str | bytes]) -> None:
    while True:
        item = await queue.get()
        if isinstance(item, bytes):
            await ws.send_bytes(item)
        else:
            await ws.send_text(item)


def _error(client: Client, code: ErrorCode, message: str) -> None:
    client.send_model(Error(code=code, message=message))


async def _pump_in(
    ws: WebSocket, client: Client, station: Station, settings: Settings, limiter: RateLimiter
) -> None:
    while True:
        message = await ws.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(code=message.get("code", 1000))
        text = message.get("text")
        if text is None:
            _error(client, "bad_message", "binary messages are not accepted")
            continue
        if len(text) > MAX_CLIENT_MESSAGE_BYTES:
            _error(client, "bad_message", "message too large")
            continue
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            _error(client, "bad_message", "not JSON")
            continue
        if isinstance(raw, dict) and raw.get("v") not in (None, 1):
            _error(
                client,
                "unsupported_version",
                f"protocol v{raw.get('v')} not supported; this bridge speaks v1",
            )
            continue
        try:
            msg: ClientMessage = client_message_adapter.validate_python(raw)
        except ValidationError as exc:
            _error(client, "bad_message", exc.errors(include_url=False)[0]["msg"])
            continue
        await _handle(msg, client, station, settings, limiter)


async def _handle(
    msg: ClientMessage, client: Client, station: Station, settings: Settings, limiter: RateLimiter
) -> None:
    if isinstance(msg, Ping):
        client.send_model(Pong(utc=station.clock.utc_now()))
        return
    if isinstance(msg, Subscribe):
        client.audio, client.waterfall = msg.audio, msg.waterfall
        return
    if not isinstance(msg, (Tune, SelectReceiver, DisconnectReceiver)):
        return  # ClientHello: informational
    if not limiter.allow():
        _error(client, "rate_limited", "too many control messages; slow down")
        return
    if isinstance(msg, Tune):
        t = msg.tuning
        if t.low_cut_hz >= t.high_cut_hz:
            _error(client, "invalid_tuning", "low cut must be below high cut")
            return
        await station.tune(
            Tuning(
                dial_hz=t.dial_hz, mode=t.mode, low_cut_hz=t.low_cut_hz, high_cut_hz=t.high_cut_hz
            )
        )
    elif isinstance(msg, SelectReceiver):
        try:
            host = validate_receiver_host(
                msg.receiver.host, allow_private=settings.allow_private_receivers
            )
        except InvalidReceiver as exc:
            _error(client, "invalid_receiver", str(exc))
            return
        log.info("receiver selected: %s:%d", host, msg.receiver.port)
        station.select_receiver(
            ReceiverTarget(host, msg.receiver.port, msg.password, msg.receiver.name)
        )
    else:
        station.disconnect_receiver()

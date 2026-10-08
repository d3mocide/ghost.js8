"""Bridge-side adapter for the native JS8Call decoder (talks to decoder-agent)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI

from ghostjs8 import __version__
from ghostjs8.decoders.base import DecodeEvent, DecoderSink, DecoderUnavailable, SpotEvent
from ghostjs8.decoders.js8call_native import agent_protocol as proto
from ghostjs8.decoders.js8call_native.messages import parse_js8_message
from ghostjs8.util.clock import Clock, SystemClock

log = logging.getLogger("ghostjs8.decoders.js8call_native")


class Js8CallNativeDecoder:
    """One decoder slot. ``run()`` raises DecoderUnavailable when the link drops."""

    def __init__(
        self,
        agent_url: str,
        sink: DecoderSink,
        *,
        clock: Clock | None = None,
        max_pending_blocks: int = 48,
        connect_timeout_s: float = 5.0,
    ) -> None:
        self.agent_url = agent_url
        self.sink = sink
        self._clock = clock or SystemClock()
        self._audio: asyncio.Queue[bytes] = asyncio.Queue(maxsize=max_pending_blocks)
        self._connect_timeout_s = connect_timeout_s
        self._ws: ClientConnection | None = None
        self.dropped_audio_blocks = 0

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def submit_audio(self, pcm_s16le: bytes) -> None:
        """Queue PCM for the decoder. Never blocks; drops oldest when full or offline."""
        if self._audio.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._audio.get_nowait()
            self.dropped_audio_blocks += 1
        self._audio.put_nowait(pcm_s16le)

    async def run(self) -> None:
        try:
            async with asyncio.timeout(self._connect_timeout_s):
                ws = await connect(self.agent_url, compression=None, max_size=2**20)
        except (TimeoutError, OSError, InvalidHandshake, InvalidURI) as exc:
            raise DecoderUnavailable(f"decoder agent {self.agent_url}: {exc}") from exc
        self._ws = ws
        # Audio queued while offline is stale; JS8 needs live, aligned audio.
        while not self._audio.empty():
            self._audio.get_nowait()
        log.info("connected to decoder agent %s", self.agent_url)
        try:
            await ws.send(json.dumps({"t": "hello", "bridge": __version__}))
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._send_audio(ws))
                tg.create_task(self._receive(ws))
        except* ConnectionClosed as eg:
            raise DecoderUnavailable(f"decoder agent link closed: {eg.exceptions[0]}") from None
        finally:
            self._ws = None
            await ws.close()

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()

    async def _send_audio(self, ws: ClientConnection) -> None:
        while True:
            await ws.send(await self._audio.get())

    async def _receive(self, ws: ClientConnection) -> None:
        async for raw in ws:
            if isinstance(raw, bytes):
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                log.warning("agent sent non-JSON text")
                continue
            if isinstance(payload, dict):
                self._dispatch(payload)
        raise ConnectionClosed(None, None)

    def _dispatch(self, payload: dict[str, Any]) -> None:
        kind = payload.get("t")
        if kind == "health":
            self.sink.on_health(proto.decode_health(payload))
        elif kind == "js8":
            msg = payload.get("msg")
            received = proto.from_utc_ms(payload.get("rx_utc_ms")) or self._clock.utc_now()
            if not isinstance(msg, dict):
                return
            for event in parse_js8_message(msg, received_utc=received):
                if isinstance(event, DecodeEvent):
                    self.sink.on_decode(event)
                elif isinstance(event, SpotEvent):
                    self.sink.on_spot(event)

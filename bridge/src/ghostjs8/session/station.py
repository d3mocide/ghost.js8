"""A station: one receiver session feeding one decoder slot, fanned out to browsers.

Owns reconnect policy for both sides (jittered exponential backoff) so adapters
stay simple and testable.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Protocol

from ghostjs8.api.hub import Hub
from ghostjs8.contract.messages import Decode
from ghostjs8.decoders.base import DecodeEvent, DecoderError, DecoderHealth, DecoderSink, SpotEvent
from ghostjs8.receivers.base import (
    AudioBlock,
    ReceiverError,
    ReceiverRejected,
    ReceiverSink,
    Tuning,
    WaterfallRow,
)
from ghostjs8.util.backoff import Backoff

log = logging.getLogger("ghostjs8.session.station")


class ReceiverHandle(Protocol):
    @property
    def tuning(self) -> Tuning: ...

    async def run(self) -> None: ...

    async def close(self) -> None: ...


class DecoderHandle(Protocol):
    def submit_audio(self, pcm_s16le: bytes) -> None: ...

    async def run(self) -> None: ...

    async def close(self) -> None: ...


ReceiverFactory = Callable[[ReceiverSink], ReceiverHandle]
DecoderFactory = Callable[[DecoderSink], DecoderHandle]


class Station(ReceiverSink, DecoderSink):
    def __init__(
        self,
        hub: Hub,
        decoder_factory: DecoderFactory,
        receiver_factory: ReceiverFactory | None = None,
        *,
        receiver_backoff: Backoff | None = None,
        decoder_backoff: Backoff | None = None,
    ) -> None:
        self.hub = hub
        self.decoder = decoder_factory(self)
        self._receiver_factory = receiver_factory
        self.receiver: ReceiverHandle | None = None
        self._receiver_backoff = receiver_backoff or Backoff()
        self._decoder_backoff = decoder_backoff or Backoff(minimum_s=1.0, maximum_s=15.0)
        self.decoder_health: DecoderHealth | None = None
        self.last_receiver_error: ReceiverError | None = None

    async def run(self) -> None:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._decoder_loop())
            if self._receiver_factory is not None:
                tg.create_task(self._receiver_loop(self._receiver_factory))

    async def _decoder_loop(self) -> None:
        while True:
            try:
                await self.decoder.run()
                self._decoder_backoff.reset()
            except DecoderError as exc:
                log.warning("decoder unavailable: %s", exc)
            await asyncio.sleep(self._decoder_backoff.next_delay())

    async def _receiver_loop(self, factory: ReceiverFactory) -> None:
        while True:
            self.receiver = factory(self)
            try:
                await self.receiver.run()
            except ReceiverRejected as exc:
                self.last_receiver_error = exc
                log.warning("receiver rejected: %s", exc)
            except ReceiverError as exc:
                self.last_receiver_error = exc
                log.warning("receiver session ended: %s", exc)
            else:
                return  # closed deliberately
            delay = self._receiver_backoff.next_delay()
            log.info("reconnecting to receiver in %.0fs", delay)
            await asyncio.sleep(delay)

    # ---------------------------------------------------------- ReceiverSink

    def on_audio(self, block: AudioBlock) -> None:
        self._receiver_backoff.reset()
        self.decoder.submit_audio(block.pcm_s16le)

    def on_waterfall(self, row: WaterfallRow) -> None:
        pass  # browser waterfall channel lands in milestone 6

    def on_info(self, key: str, value: str) -> None:
        log.debug("receiver info %s=%s", key, value)

    # ----------------------------------------------------------- DecoderSink

    def on_decode(self, event: DecodeEvent) -> None:
        dial = self.receiver.tuning.dial_hz if self.receiver is not None else None
        log.info(
            "decode %s snr=%d off=%d %s", event.kind, event.snr_db, event.offset_hz, event.text
        )
        self.hub.broadcast(
            Decode(
                kind=event.kind,
                utc=event.utc,
                text=event.text,
                snr_db=event.snr_db,
                offset_hz=event.offset_hz,
                dial_hz=dial,
                freq_hz=dial + event.offset_hz if dial is not None else None,
                speed=event.speed,
                from_call=event.from_call,
                to_call=event.to_call,
                grid=event.grid,
            )
        )

    def on_spot(self, event: SpotEvent) -> None:
        log.debug("spot %s", event.callsign)

    def on_health(self, health: DecoderHealth) -> None:
        self.decoder_health = health

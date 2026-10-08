"""A station: one receiver session feeding one decoder slot, fanned out to browsers.

Owns everything with policy in it, so adapters stay simple and testable:

- receiver lifecycle and reconnect policy (jittered backoff; no automatic retry
  after auth/redirect rejections or unsupported audio formats)
- control from browsers (tune, select / disconnect receiver)
- truthful health (``HealthTracker``) and session state broadcasts
- binary fan-out to subscribed browsers with a waterfall frame-rate cap
- persistence (decodes, heard stations) and history for new viewers
- optional idle disconnect when nobody is watching
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from pydantic import BaseModel

from ghostjs8 import __version__
from ghostjs8.api.hub import Client, Hub
from ghostjs8.contract import binary
from ghostjs8.contract.messages import (
    Decode,
    Hello,
    History,
    Limits,
    ReceiverRef,
    ReceiverStatus,
    RejectReasonName,
    Session,
    SessionState,
    TuningModel,
)
from ghostjs8.contract.messages import Station as StationMsg
from ghostjs8.decoders.base import DecodeEvent, DecoderError, DecoderHealth, DecoderSink, SpotEvent
from ghostjs8.receivers.base import (
    AUDIO_SAMPLE_RATE,
    AudioBlock,
    ReceiverError,
    ReceiverRejected,
    ReceiverSink,
    RejectReason,
    Tuning,
    UnsupportedAudioFormat,
    WaterfallRow,
)
from ghostjs8.session.health import HealthTracker
from ghostjs8.store.sqlite import Store
from ghostjs8.util.backoff import Backoff
from ghostjs8.util.clock import Clock, SystemClock
from ghostjs8.util.maidenhead import normalize_grid

log = logging.getLogger("ghostjs8.session.station")

# Rejections that a retry cannot fix: wait for the operator.
TERMINAL_REJECTIONS = frozenset({RejectReason.AUTH, RejectReason.REDIRECT})
# Rejections where the receiver is up but has no room: be patient.
PATIENT_REJECTIONS = frozenset({RejectReason.FULL, RejectReason.BUSY, RejectReason.DUPLICATE_IP})
PATIENT_MIN_DELAY_S = 60.0
ADC_OVERLOAD_HOLD_S = 2.0
STATUS_INTERVAL_S = 2.0
HEALTH_POLL_S = 1.0
HEALTH_HEARTBEAT_S = 10.0
PRUNE_INTERVAL_S = 3600.0


class ReceiverHandle(Protocol):
    @property
    def tuning(self) -> Tuning: ...

    async def run(self) -> None: ...

    async def close(self) -> None: ...

    async def retune(self, tuning: Tuning) -> None: ...


class DecoderHandle(Protocol):
    @property
    def connected(self) -> bool: ...

    def submit_audio(self, pcm_s16le: bytes) -> None: ...

    async def run(self) -> None: ...

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ReceiverTarget:
    host: str
    port: int
    password: str = ""
    name: str | None = None
    tls: bool = False


class StationObserver(Protocol):
    """Taps the station's data path (e.g. the GhostNet net recorder). Must not block."""

    def on_audio(self, block: AudioBlock) -> None: ...

    def on_waterfall(self, row: WaterfallRow) -> None: ...

    def on_decode(self, decode: Decode) -> None: ...


ReceiverFactory = Callable[[ReceiverTarget, Tuning, ReceiverSink], ReceiverHandle]
DecoderFactory = Callable[[DecoderSink], DecoderHandle]


@dataclass(frozen=True, slots=True)
class StationConfig:
    waterfall_max_fps: float = 10.0
    waterfall_bins: int = 1024
    idle_disconnect_s: float = 0.0  # 0 = keep listening with nobody watching
    history_decodes: int = 200


class Station(ReceiverSink, DecoderSink):
    def __init__(
        self,
        hub: Hub,
        decoder_factory: DecoderFactory,
        receiver_factory: ReceiverFactory | None = None,
        *,
        tuning: Tuning | None = None,
        target: ReceiverTarget | None = None,
        store: Store | None = None,
        clock: Clock | None = None,
        config: StationConfig | None = None,
        receiver_backoff: Backoff | None = None,
        decoder_backoff: Backoff | None = None,
    ) -> None:
        self.hub = hub
        self.clock = clock or SystemClock()
        self.config = config or StationConfig()
        self.health = HealthTracker(self.clock)
        self.store = store
        self.decoder = decoder_factory(self)
        self._receiver_factory = receiver_factory
        self._receiver_backoff = receiver_backoff or Backoff()
        self._decoder_backoff = decoder_backoff or Backoff(minimum_s=1.0, maximum_s=15.0)

        self.tuning = tuning or Tuning(dial_hz=14_078_000)
        self.target = target
        self.receiver: ReceiverHandle | None = None
        self.state: SessionState = "idle"
        self.reject_reason: RejectReasonName | None = None
        self.detail = ""
        self.next_retry_utc: datetime | None = None
        self._target_changed = asyncio.Event()
        self._idle_paused = False
        self._no_clients_since: float | None = self.clock.monotonic()

        self._adc_overload_until: float | None = None
        self._adc_overload_reported = False
        self._rssi: float | None = None
        self._receiver_info: dict[str, str] = {}
        self._last_wf_mono: float | None = None
        self.observers: list[StationObserver] = []
        # Called when a viewer changes tuning or receiver (the GhostNet autopilot yields).
        self.operator_action: list[Callable[[], None]] = []
        # Extra messages sent to each new viewer after the standard ones.
        self.join_messages: list[Callable[[], BaseModel]] = []

    # ================================================================ run

    async def run(self) -> None:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._decoder_loop())
            tg.create_task(self._receiver_loop())
            tg.create_task(self._health_loop())
            tg.create_task(self._status_loop())
            tg.create_task(self._idle_loop())
            if self.store is not None:
                tg.create_task(self._prune_loop())

    async def _decoder_loop(self) -> None:
        while True:
            self.health.decoder_link(False)
            try:
                await self.decoder.run()
                self._decoder_backoff.reset()
            except DecoderError as exc:
                log.warning("decoder unavailable: %s", exc)
            self.health.decoder_link(False)
            await asyncio.sleep(self._decoder_backoff.next_delay())

    async def _receiver_loop(self) -> None:
        while True:
            self._target_changed.clear()
            target = self.target
            if target is None or self._receiver_factory is None or self._idle_paused:
                self._set_state("idle", detail="nobody watching" if self._idle_paused else "")
                await self._target_changed.wait()
                continue
            self._set_state("connecting", detail=f"{target.host}:{target.port}")
            self.receiver = self._receiver_factory(target, self.tuning, self)
            run = asyncio.create_task(self.receiver.run())
            changed = asyncio.create_task(self._target_changed.wait())
            await asyncio.wait({run, changed}, return_when=asyncio.FIRST_COMPLETED)
            if not run.done():  # operator changed target (or idle pause): restart now
                await self.receiver.close()
                with contextlib.suppress(ReceiverError, asyncio.CancelledError):
                    await run
                changed.cancel()
                self._receiver_backoff.reset()
                continue
            changed.cancel()
            delay = self._after_receiver_ended(run)
            self.receiver = None
            if delay is None:
                await self._target_changed.wait()  # terminal: wait for the operator
                continue
            self.next_retry_utc = self.clock.utc_now() + timedelta(seconds=delay)
            self._broadcast_session()
            log.info("reconnecting to receiver in %.0fs", delay)
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(delay):
                    await self._target_changed.wait()
            self.next_retry_utc = None

    def _after_receiver_ended(self, run: asyncio.Task[None]) -> float | None:
        """Classify how a receiver session ended. Returns retry delay, or None to stop."""
        exc = run.exception()
        if exc is None:
            self._set_state("idle", detail="closed")
            return None
        if isinstance(exc, ReceiverRejected):
            log.warning("receiver rejected: %s", exc)
            if exc.reason in TERMINAL_REJECTIONS:
                self._set_state("rejected", reason=exc.reason.value, detail=str(exc))
                return None
            delay = self._receiver_backoff.next_delay()
            if exc.reason in PATIENT_REJECTIONS:
                delay = max(delay, PATIENT_MIN_DELAY_S)
            self._set_state("rejected", reason=exc.reason.value, detail=str(exc))
            return delay
        if isinstance(exc, UnsupportedAudioFormat):
            log.error("receiver sends unsupported audio: %s", exc)
            self._set_state("failed", detail=str(exc))
            return None
        if isinstance(exc, ReceiverError):
            log.warning("receiver session ended: %s", exc)
            self._set_state("backoff", detail=str(exc))
            return self._receiver_backoff.next_delay()
        raise exc

    async def _health_loop(self) -> None:
        last_sent = -1e9
        while True:
            snap, changed = self.health.poll()
            now = self.clock.monotonic()
            if changed or now - last_sent >= HEALTH_HEARTBEAT_S:
                self.hub.broadcast(snap)
                last_sent = now
            await asyncio.sleep(HEALTH_POLL_S)

    async def _status_loop(self) -> None:
        while True:
            if self.state == "connected":
                self.hub.broadcast(self.receiver_status())
            await asyncio.sleep(STATUS_INTERVAL_S)

    async def _idle_loop(self) -> None:
        limit = self.config.idle_disconnect_s
        if limit <= 0:
            return
        while True:
            await asyncio.sleep(1.0)
            idle_since = self._no_clients_since
            if (
                not self._idle_paused
                and idle_since is not None
                and self.clock.monotonic() - idle_since >= limit
                and self.target is not None
            ):
                log.info("no viewers for %.0fs: releasing receiver", limit)
                self._idle_paused = True
                self._target_changed.set()

    async def _prune_loop(self) -> None:
        while True:
            if self.store is not None:
                removed = self.store.prune()
                if removed:
                    log.info("pruned %d expired records", removed)
            await asyncio.sleep(PRUNE_INTERVAL_S)

    # ============================================================ control

    def select_receiver(self, target: ReceiverTarget) -> None:
        self.target = target
        self._receiver_backoff.reset()
        self._target_changed.set()

    def disconnect_receiver(self) -> None:
        self.target = None
        self._target_changed.set()

    async def tune(self, tuning: Tuning) -> None:
        self.tuning = tuning
        if self.receiver is not None:
            try:
                await self.receiver.retune(tuning)
            except ReceiverError as exc:
                log.warning("retune failed: %s", exc)
        self._broadcast_session()

    def operator_changed(self) -> None:
        """A viewer took manual control (tune / select / release)."""
        for callback in self.operator_action:
            callback()

    def client_joined(self, client: Client) -> None:
        self._no_clients_since = None
        if self._idle_paused:
            self._idle_paused = False
            self._target_changed.set()
        client.send_model(
            Hello(
                build=__version__,
                limits=Limits(
                    max_clients=self.hub.max_clients,
                    audio_sample_rate=AUDIO_SAMPLE_RATE,
                    waterfall_max_fps=self.config.waterfall_max_fps,
                    waterfall_bins=self.config.waterfall_bins,
                ),
            )
        )
        if self.store is not None:
            client.send_model(
                History(
                    decodes=self.store.recent_decodes(self.config.history_decodes),
                    stations=list(reversed(self.store.stations())),
                )
            )
        client.send_model(self.session_message())
        client.send_model(self.health.snapshot())
        client.send_model(self.receiver_status())
        for make in self.join_messages:
            client.send_model(make())
        self._broadcast_session()  # subscriber count changed

    def client_left(self) -> None:
        if self.hub.client_count == 0:
            self._no_clients_since = self.clock.monotonic()
        self._broadcast_session()

    # ========================================================== messages

    def session_message(self) -> Session:
        t = self.target
        return Session(
            state=self.state,
            receiver=ReceiverRef(host=t.host, port=t.port, name=t.name) if t else None,
            tuning=TuningModel(
                dial_hz=self.tuning.dial_hz,
                mode=self.tuning.mode,
                low_cut_hz=self.tuning.low_cut_hz,
                high_cut_hz=self.tuning.high_cut_hz,
            ),
            subscribers=self.hub.client_count,
            reject_reason=self.reject_reason,
            detail=self.detail,
            next_retry_utc=self.next_retry_utc,
        )

    def receiver_status(self) -> ReceiverStatus:
        return ReceiverStatus(
            adc_overload=self._adc_overload_active(),
            rssi_dbm=round(self._rssi, 1) if self._rssi is not None else None,
            info=dict(self._receiver_info),
        )

    def _set_state(
        self, state: SessionState, *, reason: RejectReasonName | None = None, detail: str = ""
    ) -> None:
        self.state, self.reject_reason, self.detail = state, reason, detail
        self.health.receiver(state, detail)
        if state != "connected":
            self._adc_overload_until = None
            self._rssi = None
        self._broadcast_session()

    def _broadcast_session(self) -> None:
        self.hub.broadcast(self.session_message())

    def _adc_overload_active(self) -> bool:
        until = self._adc_overload_until
        return until is not None and self.clock.monotonic() < until

    # ======================================================= ReceiverSink

    def on_audio(self, block: AudioBlock) -> None:
        if self.state != "connected":
            self._set_state("connected", detail=self.target.host if self.target else "")
            self._receiver_backoff.reset()
        self.health.audio()
        self._rssi = block.rssi_dbm
        if block.adc_overload:
            self._adc_overload_until = self.clock.monotonic() + ADC_OVERLOAD_HOLD_S
        overload = self._adc_overload_active()
        if overload != self._adc_overload_reported:
            self._adc_overload_reported = overload
            self.hub.broadcast(self.receiver_status())
        self.decoder.submit_audio(block.pcm_s16le)
        for obs in self.observers:
            obs.on_audio(block)
        if self.hub.wants("audio"):
            self.hub.broadcast_binary(
                "audio",
                binary.encode_audio(
                    block.seq, AUDIO_SAMPLE_RATE, block.pcm_s16le, adc_overload=block.adc_overload
                ),
            )

    def on_waterfall(self, row: WaterfallRow) -> None:
        self.health.waterfall()
        for obs in self.observers:
            obs.on_waterfall(row)
        if not self.hub.wants("waterfall"):
            return
        now = self.clock.monotonic()
        min_gap = 1.0 / self.config.waterfall_max_fps
        if self._last_wf_mono is not None and now - self._last_wf_mono < min_gap * 0.95:
            return
        self._last_wf_mono = now
        self.hub.broadcast_binary(
            "waterfall", binary.encode_waterfall(row.seq, row.start_hz, row.span_hz, row.bins)
        )

    def on_info(self, key: str, value: str) -> None:
        self._receiver_info[key] = value

    # ======================================================== DecoderSink

    def on_decode(self, event: DecodeEvent) -> None:
        dial = self.tuning.dial_hz
        grid = normalize_grid(event.grid)
        msg = Decode(
            kind=event.kind,
            utc=event.utc,
            text=event.text,
            snr_db=event.snr_db,
            offset_hz=event.offset_hz,
            dial_hz=dial,
            freq_hz=dial + event.offset_hz,
            speed=event.speed,
            from_call=event.from_call,
            to_call=event.to_call,
            grid=grid,
        )
        self.health.decoded(event.utc)
        log.info(
            "decode %s snr=%d off=%d %s", event.kind, event.snr_db, event.offset_hz, event.text
        )
        if self.store is not None:
            self.store.add_decode(msg)
        self.hub.broadcast(msg)
        for obs in self.observers:
            obs.on_decode(msg)
        # JS8Call reports directed traffic twice (activity + directed): count the
        # activity line; the directed copy only contributes a grid, if it has one.
        if event.from_call:
            if event.kind == "activity":
                self._heard(
                    event.from_call, event.utc, event.snr_db, grid, event.offset_hz, count=True
                )
            elif grid:
                self._heard(
                    event.from_call, event.utc, event.snr_db, grid, event.offset_hz, count=False
                )

    def on_spot(self, event: SpotEvent) -> None:
        self._heard(
            event.callsign,
            event.utc,
            event.snr_db,
            normalize_grid(event.grid),
            event.offset_hz,
            count=False,
        )

    def on_health(self, health: DecoderHealth) -> None:
        self.health.decoder_link(self.decoder.connected)
        self.health.decoder_facts(health)

    def _heard(
        self,
        callsign: str,
        utc: datetime,
        snr: int | None,
        grid: str | None,
        offset: int | None,
        *,
        count: bool,
    ) -> None:
        call = callsign.strip().upper()
        if not call or call.startswith("@") or len(call) > 16:
            return  # groups (@ALLCALL, @HB) are not stations
        if self.store is not None:
            station = self.store.heard(
                call,
                utc,
                snr_db=snr,
                grid=grid,
                offset_hz=offset,
                dial_hz=self.tuning.dial_hz,
                count=count,
            )
        else:
            station = StationMsg(
                callsign=call,
                last_heard_utc=utc,
                snr_db=snr,
                grid=grid,
                offset_hz=offset,
                dial_hz=self.tuning.dial_hz,
            )
        self.hub.broadcast(station)

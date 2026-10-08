"""KiwiSDR receiver adapter: a paired SND + W/F WebSocket session.

Both streams are opened under one session identifier (the path component in
``/<id>/SND`` and ``/<id>/W/F``). Audio is normalized to mono s16le at 12 kHz;
anything else is a typed, logged, fatal error. The adapter never retries; the
session layer owns reconnect policy.

Etiquette: identifies as ``ghost.js8``, sends keepalives, only touches
per-channel settings (mode, passband, frequency, this channel's AGC, waterfall
zoom/speed). It never changes attenuation or any other shared hardware setting.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus, InvalidURI

from ghostjs8.receivers.base import (
    AUDIO_SAMPLE_RATE,
    AudioBlock,
    FrameError,
    MalformedFrame,
    ReceiverClosed,
    ReceiverError,
    ReceiverSink,
    ReceiverTimeout,
    ReceiverUnreachable,
    SessionPairingError,
    Tuning,
    UnsupportedAudioFormat,
    WaterfallRow,
)
from ghostjs8.receivers.kiwisdr import framing
from ghostjs8.util.clock import Clock, SystemClock

log = logging.getLogger("ghostjs8.receivers.kiwisdr")

StreamKind = Literal["SND", "W/F"]

IDENT = "ghost.js8"
DEFAULT_BANDWIDTH_HZ = 30_000_000
# Allowed deviation of the receiver's reported true sample rate from nominal.
SAMPLE_RATE_TOLERANCE = 0.01
# Compressed frames already in flight when compression=0 is sent are dropped
# for this long before compressed audio becomes a fatal error.
COMPRESSION_GRACE_S = 2.0
# Consecutive malformed frames before the session is abandoned.
MAX_CONSECUTIVE_BAD_FRAMES = 50

# MSG keys forwarded to the sink as receiver info.
INFO_KEYS = frozenset(
    {
        "version_maj",
        "version_min",
        "bandwidth",
        "sample_rate",
        "audio_rate",
        "freq_offset",
        "rx_chans",
        "chan_no_pwd",
        "max_camp",
    }
)

Connector = Callable[[str], "contextlib.AbstractAsyncContextManager[ClientConnection]"]


@dataclass(frozen=True, slots=True)
class KiwiEndpoint:
    host: str
    port: int = 8073
    password: str = ""
    tls: bool = False

    def stream_url(self, session_id: int, stream: StreamKind) -> str:
        scheme = "wss" if self.tls else "ws"
        return f"{scheme}://{self.host}:{self.port}/{session_id}/{stream}"


def session_id_from_url(url: str) -> int:
    parts = url.split("/")
    try:
        return int(parts[3])
    except (IndexError, ValueError) as exc:
        raise SessionPairingError(f"no session identifier in {url!r}") from exc


def verify_pairing(snd_url: str, wf_url: str) -> int:
    """Return the shared session id, or raise if the two streams differ."""
    snd_id, wf_id = session_id_from_url(snd_url), session_id_from_url(wf_url)
    if snd_id != wf_id:
        raise SessionPairingError(f"SND session {snd_id} != W/F session {wf_id}")
    return snd_id


def passband_for(tuning: Tuning) -> tuple[int, int]:
    """Kiwi passband edges: positive for USB, negative (mirrored) for LSB."""
    if tuning.mode == "usb":
        return tuning.low_cut_hz, tuning.high_cut_hz
    return -tuning.high_cut_hz, -tuning.low_cut_hz


def passband_center_hz(tuning: Tuning) -> int:
    lo, hi = passband_for(tuning)
    return tuning.dial_hz + (lo + hi) // 2


def _default_connector(url: str) -> contextlib.AbstractAsyncContextManager[ClientConnection]:
    return connect(
        url,
        compression=None,
        open_timeout=None,  # the adapter applies its own timeout
        ping_interval=None,  # Kiwi uses application-level keepalives
        max_size=2**20,
        user_agent_header=IDENT,
    )


class KiwiReceiver:
    """One paired session against one KiwiSDR."""

    def __init__(
        self,
        endpoint: KiwiEndpoint,
        tuning: Tuning,
        sink: ReceiverSink,
        *,
        waterfall: bool = True,
        wf_span_hz: int = 12_000,
        wf_speed: int = 3,
        session_id: int | None = None,
        clock: Clock | None = None,
        connect_timeout_s: float = 10.0,
        handshake_timeout_s: float = 15.0,
        keepalive_interval_s: float = 2.0,
        compression_grace_s: float = COMPRESSION_GRACE_S,
        connector: Connector = _default_connector,
    ) -> None:
        self.endpoint = endpoint
        self.sink = sink
        self._tuning = tuning
        self._waterfall = waterfall
        self._wf_span_hz = wf_span_hz
        self._wf_speed = wf_speed
        self._clock = clock or SystemClock()
        self.session_id = (
            session_id if session_id is not None else int(self._clock.utc_now().timestamp())
        )
        self._connect_timeout_s = connect_timeout_s
        self._handshake_timeout_s = handshake_timeout_s
        self._keepalive_interval_s = keepalive_interval_s
        self._compression_grace_s = compression_grace_s
        self._closing = False
        self._connector = connector

        self._snd: ClientConnection | None = None
        self._wf: ClientConnection | None = None
        self._audio_started = asyncio.Event()
        self._compression_off_at: float | None = None
        self._bandwidth_hz = DEFAULT_BANDWIDTH_HZ
        self._freq_offset_hz = 0
        self._kiwi_version: tuple[int, int] | None = None
        self._bad_frames = 0
        self.stats = {"snd_frames": 0, "wf_frames": 0, "dropped_frames": 0}

    @property
    def tuning(self) -> Tuning:
        return self._tuning

    # ------------------------------------------------------------------ run

    async def run(self) -> None:
        """Connect both streams and pump frames until closed or failed.

        Raises a ReceiverError subclass on any failure; returns only after
        ``close()``.
        """
        snd_url = self.endpoint.stream_url(self.session_id, "SND")
        wf_url = self.endpoint.stream_url(self.session_id, "W/F")
        verify_pairing(snd_url, wf_url)
        logx = {"session": self.session_id, "host": self.endpoint.host}

        async with contextlib.AsyncExitStack() as stack:
            self._snd = await self._open(stack, snd_url)
            await self._send(self._snd, f"SET auth t=kiwi p={self.endpoint.password}")
            if self._waterfall:
                self._wf = await self._open(stack, wf_url)
                await self._send(self._wf, f"SET auth t=kiwi p={self.endpoint.password}")
            log.info("kiwi streams open", extra=logx)
            failure: ReceiverError | None = None
            try:
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._read_snd(self._snd))
                    tg.create_task(self._keepalive(self._snd))
                    tg.create_task(self._handshake_watchdog())
                    if self._wf is not None:
                        tg.create_task(self._read_wf(self._wf))
                        tg.create_task(self._keepalive(self._wf))
            except* ReceiverError as eg:
                first = eg.exceptions[0]
                failure = first if isinstance(first, ReceiverError) else None
            finally:
                self._snd = self._wf = None
            if failure is not None and not self._closing:
                raise failure

    async def close(self) -> None:
        """End the session. ``run()`` then returns normally."""
        self._closing = True
        for ws in (self._snd, self._wf):
            if ws is not None:
                with contextlib.suppress(Exception):
                    await ws.close()

    async def retune(self, tuning: Tuning) -> None:
        self._tuning = tuning
        if self._snd is not None:
            await self._send_mod(self._snd)
        if self._wf is not None:
            await self._send_wf_view(self._wf)

    # ------------------------------------------------------------ plumbing

    async def _open(self, stack: contextlib.AsyncExitStack, url: str) -> ClientConnection:
        try:
            async with asyncio.timeout(self._connect_timeout_s):
                return await stack.enter_async_context(self._connector(url))
        except TimeoutError as exc:
            raise ReceiverTimeout(f"connect to {url} timed out") from exc
        except InvalidStatus as exc:
            raise ReceiverUnreachable(f"{url}: HTTP {exc.response.status_code}") from exc
        except (InvalidHandshake, InvalidURI) as exc:
            raise ReceiverUnreachable(f"{url}: not a KiwiSDR WebSocket ({exc})") from exc
        except (OSError, socket.gaierror) as exc:
            raise ReceiverUnreachable(f"{url}: {exc}") from exc

    async def _send(self, ws: ClientConnection, text: str) -> None:
        try:
            await ws.send(text)
        except ConnectionClosed as exc:
            raise ReceiverClosed(f"connection closed while sending: {exc}") from exc

    async def _keepalive(self, ws: ClientConnection) -> None:
        while True:
            await asyncio.sleep(self._keepalive_interval_s)
            await self._send(ws, "SET keepalive")

    async def _handshake_watchdog(self) -> None:
        try:
            async with asyncio.timeout(self._handshake_timeout_s):
                await self._audio_started.wait()
        except TimeoutError as exc:
            raise ReceiverTimeout(
                f"no audio within {self._handshake_timeout_s:.0f}s of connecting"
            ) from exc

    # ---------------------------------------------------------------- SND

    async def _read_snd(self, ws: ClientConnection) -> None:
        try:
            async for raw in ws:
                frame = self._parse(raw, "SND")
                if isinstance(frame, framing.MsgFrame):
                    await self._on_snd_msg(ws, frame)
                elif isinstance(frame, framing.SndFrame):
                    self._on_snd(frame)
        except ConnectionClosed as exc:
            raise ReceiverClosed(f"SND stream closed: {exc}") from exc
        raise ReceiverClosed("SND stream ended")

    async def _on_snd_msg(self, ws: ClientConnection, frame: framing.MsgFrame) -> None:
        for name, value in frame.params:
            self._check_common(name, value)
            if name == "audio_rate":
                rate = int(value or 0)
                if rate != AUDIO_SAMPLE_RATE:
                    raise UnsupportedAudioFormat(
                        "sample_rate", f"receiver audio_rate={rate}, need 12000"
                    )
                await self._send(ws, f"SET AR OK in={rate} out=44100")
            elif name == "sample_rate":
                true_rate = float(value or 0)
                if abs(true_rate - AUDIO_SAMPLE_RATE) / AUDIO_SAMPLE_RATE > SAMPLE_RATE_TOLERANCE:
                    raise UnsupportedAudioFormat("sample_rate", f"receiver sample_rate={true_rate}")
                await self._send(ws, "SET compression=0")
                self._compression_off_at = self._clock.monotonic()
                # This channel's own AGC (per-channel DSP, not shared hardware).
                await self._send(ws, "SET agc=1 hang=0 thresh=-100 slope=6 decay=1000 manGain=50")
                await self._send_mod(ws)
                await self._send(ws, f"SET ident_user={IDENT}")
                await self._send(ws, "SET keepalive")

    def _on_snd(self, frame: framing.SndFrame) -> None:
        if frame.flags & framing.SND_FLAG_COMPRESSED and self._in_compression_grace():
            self.stats["dropped_frames"] += 1
            return
        try:
            pcm = framing.snd_to_s16le(frame)  # UnsupportedAudioFormat propagates: fatal
        except MalformedFrame as exc:
            self._bad_frame(exc)
            return
        self._bad_frames = 0
        self.stats["snd_frames"] += 1
        self._audio_started.set()
        self.sink.on_audio(
            AudioBlock(
                seq=frame.seq,
                pcm_s16le=pcm,
                rssi_dbm=frame.rssi_dbm,
                adc_overload=frame.adc_overload,
            )
        )

    def _in_compression_grace(self) -> bool:
        if self._compression_off_at is None:
            return True  # compression=0 not sent yet; nothing should be flowing
        return self._clock.monotonic() - self._compression_off_at < self._compression_grace_s

    async def _send_mod(self, ws: ClientConnection) -> None:
        lo, hi = passband_for(self._tuning)
        freq_khz = (self._tuning.dial_hz - self._freq_offset_hz) / 1000
        await self._send(
            ws, f"SET mod={self._tuning.mode} low_cut={lo} high_cut={hi} freq={freq_khz:.3f}"
        )

    # ---------------------------------------------------------------- W/F

    async def _read_wf(self, ws: ClientConnection) -> None:
        try:
            async for raw in ws:
                frame = self._parse(raw, "W/F")
                if isinstance(frame, framing.MsgFrame):
                    await self._on_wf_msg(ws, frame)
                elif isinstance(frame, framing.WfFrame):
                    self._on_wf(frame)
        except ConnectionClosed as exc:
            raise ReceiverClosed(f"W/F stream closed: {exc}") from exc
        raise ReceiverClosed("W/F stream ended")

    async def _on_wf_msg(self, ws: ClientConnection, frame: framing.MsgFrame) -> None:
        for name, value in frame.params:
            self._check_common(name, value)
            if name == "wf_setup":
                await self._send_wf_view(ws)
                await self._send(ws, "SET maxdb=-10 mindb=-110")
                await self._send(ws, f"SET wf_speed={self._wf_speed}")
                await self._send(ws, "SET wf_comp=0")
                await self._send(ws, "SET interp=13")
                await self._send(ws, f"SET ident_user={IDENT}")
                await self._send(ws, "SET keepalive")

    def _on_wf(self, frame: framing.WfFrame) -> None:
        if len(frame.bins) != framing.WF_BINS:
            self._bad_frame(MalformedFrame(f"W/F row has {len(frame.bins)} bins, expected 1024"))
            return
        self.stats["wf_frames"] += 1
        self.sink.on_waterfall(
            WaterfallRow(
                seq=frame.seq,
                start_hz=framing.wf_start_hz(frame.x_bin, self._bandwidth_hz)
                + self._freq_offset_hz,
                span_hz=framing.wf_span_hz(frame.zoom, self._bandwidth_hz),
                bins=frame.bins,
            )
        )

    async def _send_wf_view(self, ws: ClientConnection) -> None:
        zoom = framing.wf_zoom_for_span(self._wf_span_hz, self._bandwidth_hz)
        center_khz = (passband_center_hz(self._tuning) - self._freq_offset_hz) / 1000
        if self._kiwi_version is None or self._kiwi_version >= (1, 329):
            await self._send(ws, f"SET zoom={zoom} cf={center_khz:.3f}")
        else:  # pre-1.329 servers only understand a start counter
            span_khz = self._bandwidth_hz / 1000 / 2**zoom
            start_khz = max(0.0, center_khz - span_khz / 2)
            full = framing.WF_BINS * 2**framing.WF_MAX_ZOOM
            counter = round(start_khz / (self._bandwidth_hz / 1000) * full)
            await self._send(ws, f"SET zoom={zoom} start={counter}")

    # -------------------------------------------------------------- shared

    def _parse(self, raw: bytes | str, stream: StreamKind) -> framing.Frame | None:
        try:
            return framing.parse_frame(raw)
        except MalformedFrame as exc:
            self._bad_frame(exc)
            return None

    def _bad_frame(self, exc: FrameError) -> None:
        self._bad_frames += 1
        self.stats["dropped_frames"] += 1
        log.warning("dropped frame: %s", exc, extra={"session": self.session_id})
        if self._bad_frames >= MAX_CONSECUTIVE_BAD_FRAMES:
            raise ReceiverClosed(f"{self._bad_frames} consecutive bad frames; last: {exc}")

    def _check_common(self, name: str, value: str | None) -> None:
        rejection = framing.rejection_from_msg(name, value)
        if rejection is not None:
            log.warning("kiwi rejected session: %s", rejection, extra={"session": self.session_id})
            raise rejection
        if name == "bandwidth" and value:
            self._bandwidth_hz = int(float(value))
        elif name == "freq_offset" and value:
            self._freq_offset_hz = round(float(value) * 1000)  # kHz on the wire
        elif name == "version_maj" and value:
            self._kiwi_version = (int(value), self._kiwi_version[1] if self._kiwi_version else 0)
        elif name == "version_min" and value and self._kiwi_version is not None:
            self._kiwi_version = (self._kiwi_version[0], int(value))
        if name in INFO_KEYS and value is not None:
            self.sink.on_info(name, value)

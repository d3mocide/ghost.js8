"""Receiver adapter interface: what the bridge needs from any SDR input.

A receiver produces normalized audio (12 kHz, mono, signed 16-bit
little-endian PCM), waterfall rows, and status. Adapters raise the typed errors
below; they never retry on their own (reconnect policy lives in the session
layer so it can be shared and tested).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Literal, Protocol

AUDIO_SAMPLE_RATE = 12_000
"""The only audio rate the decoder path supports."""

Mode = Literal["usb", "lsb"]


@dataclass(frozen=True, slots=True)
class Tuning:
    """What to listen to. Frequencies in Hz; passband edges relative to the dial."""

    dial_hz: int
    mode: Mode = "usb"
    low_cut_hz: int = 100
    high_cut_hz: int = 3000

    def __post_init__(self) -> None:
        if not 0 < self.dial_hz < 100_000_000:
            raise ValueError(f"dial_hz out of range: {self.dial_hz}")
        if not 0 <= self.low_cut_hz < self.high_cut_hz <= 6000:
            raise ValueError(f"bad passband {self.low_cut_hz}..{self.high_cut_hz} Hz")


@dataclass(frozen=True, slots=True)
class AudioBlock:
    """Normalized PCM: mono s16le at AUDIO_SAMPLE_RATE."""

    seq: int
    pcm_s16le: bytes
    rssi_dbm: float
    adc_overload: bool

    @property
    def samples(self) -> int:
        return len(self.pcm_s16le) // 2


@dataclass(frozen=True, slots=True)
class WaterfallRow:
    """One waterfall line. Bin values are u8 where dBm ~= value - 255 (before cal)."""

    seq: int
    start_hz: int
    span_hz: int
    bins: bytes


class ReceiverSink(Protocol):
    """Where an adapter delivers data. Implementations must not block."""

    def on_audio(self, block: AudioBlock) -> None: ...

    def on_waterfall(self, row: WaterfallRow) -> None: ...

    def on_info(self, key: str, value: str) -> None:
        """Informational receiver metadata (version, users, sample rate, ...)."""
        ...


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class ReceiverError(Exception):
    """Base for everything a receiver adapter raises."""


class RejectReason(enum.StrEnum):
    FULL = "full"  # all client slots taken
    BUSY = "busy"  # temporarily unavailable (db update, starting up, ...)
    AUTH = "auth"  # password required / wrong
    DOWN = "down"  # receiver says it is down
    REDIRECT = "redirect"  # receiver wants us elsewhere
    DUPLICATE_IP = "duplicate_ip"  # no multiple connections from one address


class ReceiverRejected(ReceiverError):
    def __init__(self, reason: RejectReason, detail: str = "") -> None:
        super().__init__(
            f"receiver rejected connection: {reason.value}{': ' + detail if detail else ''}"
        )
        self.reason = reason
        self.detail = detail


class ReceiverUnreachable(ReceiverError):
    """DNS failure, refused connection, bad host, or a non-WebSocket answer."""


class ReceiverTimeout(ReceiverError):
    """Connect or handshake did not complete in time."""


class ReceiverClosed(ReceiverError):
    """The receiver ended an established session."""


class SessionPairingError(ReceiverError):
    """SND and W/F streams were not opened under the same session identifier."""


class FrameError(ReceiverError):
    """A frame could not be used. Logged and counted; does not end the session."""


class MalformedFrame(FrameError):
    """Truncated or structurally invalid frame."""


AudioFormatKind = Literal["compressed", "stereo", "iq", "sample_rate"]


class UnsupportedAudioFormat(ReceiverError):
    """The receiver is sending audio we deliberately do not handle.

    Fatal for the session: a decoder fed the wrong format fails silently.
    """

    def __init__(self, kind: AudioFormatKind, detail: str = "") -> None:
        super().__init__(f"unsupported audio format: {kind}{': ' + detail if detail else ''}")
        self.kind: AudioFormatKind = kind
        self.detail = detail

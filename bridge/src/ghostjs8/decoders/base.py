"""Decoder adapter interface.

A decoder consumes normalized audio (mono s16le, 12 kHz) and produces decode
events plus health facts. Today: native JS8Call behind an in-container agent.
Tomorrow: a WASM build. The bridge only sees this interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

DecodeKind = Literal["activity", "directed"]


@dataclass(frozen=True, slots=True)
class DecodeEvent:
    kind: DecodeKind
    utc: datetime  # time JS8Call attributes to the transmission
    text: str  # display text; directed traffic is "FROM: TO ..." like JS8Call's UI
    snr_db: int
    offset_hz: int  # audio offset within the passband
    speed: str  # JS8 submode: normal, fast, turbo, slow, ultra
    from_call: str | None = None
    to_call: str | None = None
    grid: str | None = None
    tdrift_s: float | None = None


@dataclass(frozen=True, slots=True)
class SpotEvent:
    """A station heard, from RX.SPOT / RX.CALL_ACTIVITY."""

    callsign: str
    utc: datetime
    snr_db: int | None = None
    offset_hz: int | None = None
    grid: str | None = None


@dataclass(frozen=True, slots=True)
class DecoderHealth:
    """Facts reported by the decoder, each with the time it was last true."""

    process_up: bool
    capturing: bool  # decoder holds a live audio capture stream
    last_ping_utc: datetime | None  # decoder API heartbeat (JS8Call PING)
    last_api_reply_utc: datetime | None  # round trip: request -> reply
    last_audio_write_utc: datetime | None  # audio last delivered into the decoder input
    dropped_audio_blocks: int = 0
    details: dict[str, str] = field(default_factory=dict)


class DecoderSink(Protocol):
    def on_decode(self, event: DecodeEvent) -> None: ...

    def on_spot(self, event: SpotEvent) -> None: ...

    def on_health(self, health: DecoderHealth) -> None: ...


class DecoderError(Exception):
    """Base for decoder adapter failures."""


class DecoderUnavailable(DecoderError):
    """The decoder cannot be reached (agent down, container restarting)."""

"""Bridge <-> browser protocol: the single source of truth.

JSON text frames are discriminated unions on ``type`` and carry the protocol
version ``v``. JSON Schema (``contract/schema.json``) and TypeScript
(``web/src/lib/protocol/generated.ts``) are generated from these models with
``make contract``; never edit the generated files by hand. CI fails on drift.

Binary frames (audio, waterfall) are documented in docs/protocol.md and
implemented in ``ghostjs8.contract.binary``.

This is a receive-only protocol: there is deliberately no message that could
transmit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ghostjs8 import PROTOCOL_VERSION

Mode = Literal["usb", "lsb"]
ComponentState = Literal["ok", "degraded", "down", "unknown"]
SessionState = Literal["idle", "connecting", "connected", "backoff", "rejected", "failed"]
RejectReasonName = Literal["full", "busy", "auth", "down", "redirect", "duplicate_ip"]
ErrorCode = Literal[
    "bad_message",
    "unsupported_version",
    "session_full",
    "invalid_tuning",
    "invalid_receiver",
    "rate_limited",
    "internal",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Msg(_Model):
    v: Literal[1] = PROTOCOL_VERSION


# ----------------------------------------------------------------- shared


class TuningModel(_Model):
    dial_hz: int = Field(gt=0, lt=100_000_000)
    mode: Mode = "usb"
    low_cut_hz: int = Field(default=100, ge=0, le=6000)
    high_cut_hz: int = Field(default=3000, ge=0, le=6000)


class ReceiverRef(_Model):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=8073, ge=1, le=65535)
    name: str | None = None


class Limits(_Model):
    max_clients: int
    audio_sample_rate: int
    waterfall_max_fps: float
    waterfall_bins: int


class Component(_Model):
    state: ComponentState
    since: datetime  # when the state last changed
    last_seen: datetime | None = None  # last positive evidence, if any
    detail: str = ""


class Components(_Model):
    bridge: Component
    decoder_process: Component  # JS8Call process running (and agent reachable)
    decoder_api: Component  # JS8Call UDP API answering (PING / request round trip)
    decoder_capture: Component  # JS8Call holds a live capture stream on its input
    receiver: Component  # receiver session connected
    audio: Component  # fresh audio arriving from the receiver
    waterfall: Component  # fresh waterfall rows arriving


# ---------------------------------------------------------- server -> client


class Hello(_Msg):
    """First message on every connection."""

    type: Literal["hello"] = "hello"
    server: str = "ghost.js8"
    build: str
    receive_only: Literal[True] = True
    limits: Limits | None = None


class Health(_Msg):
    """Truthful readiness: distinct components, each with evidence timestamps."""

    type: Literal["health"] = "health"
    utc: datetime
    overall: Literal["listening", "degraded", "offline"]
    components: Components
    last_decode_utc: datetime | None = None


class Session(_Msg):
    type: Literal["session"] = "session"
    state: SessionState
    receiver: ReceiverRef | None = None
    tuning: TuningModel
    subscribers: int
    reject_reason: RejectReasonName | None = None
    detail: str = ""
    next_retry_utc: datetime | None = None


class Decode(_Msg):
    """One decoded JS8 transmission. ``utc`` comes from the decoder, never inferred."""

    type: Literal["decode"] = "decode"
    kind: Literal["activity", "directed"]
    utc: datetime
    text: str
    snr_db: int
    offset_hz: int
    dial_hz: int | None = None
    freq_hz: int | None = None
    speed: str
    from_call: str | None = None
    to_call: str | None = None
    grid: str | None = None  # valid Maidenhead only


class Station(_Msg):
    """A heard station. ``grid`` is present only when it is a valid Maidenhead locator."""

    type: Literal["station"] = "station"
    callsign: str
    last_heard_utc: datetime
    snr_db: int | None = None
    grid: str | None = None
    offset_hz: int | None = None
    dial_hz: int | None = None
    heard_count: int = 1


class History(_Msg):
    """Sent once after hello: recent traffic from the store, oldest first."""

    type: Literal["history"] = "history"
    decodes: list[Decode]
    stations: list[Station]


class ReceiverStatus(_Msg):
    type: Literal["receiver_status"] = "receiver_status"
    adc_overload: bool
    rssi_dbm: float | None = None
    info: dict[str, str] = Field(default_factory=dict)


class Error(_Msg):
    type: Literal["error"] = "error"
    code: ErrorCode
    message: str


class GhostNetWindow(_Model):
    id: str
    label: str
    kind: Literal["net", "bridge"]
    band: str
    dial_hz: int
    start: datetime
    end: datetime


class GhostNet(_Msg):
    """GhostNet autopilot status (absent features report enabled = false)."""

    type: Literal["ghostnet"] = "ghostnet"
    enabled: bool
    region: Literal["na", "eu", "aus"] | None
    home_grid: str | None
    mode: Literal["off", "window", "parked", "paused"]
    window: GhostNetWindow | None  # the window being monitored (pre-roll included)
    next_window: GhostNetWindow | None
    recording_net_id: str | None
    receiver_reason: str
    paused_until: datetime | None
    detail: str


class Pong(_Msg):
    type: Literal["pong"] = "pong"
    utc: datetime


ServerMessage = Annotated[
    Hello
    | Health
    | Session
    | Decode
    | Station
    | History
    | ReceiverStatus
    | GhostNet
    | Error
    | Pong,
    Field(discriminator="type"),
]
server_message_adapter: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)


# ------------------------------------------------------------- HTTP API


class ReceiverListing(_Model):
    """One public receiver from the directory (GET /api/receivers)."""

    id: str
    name: str
    host: str
    port: int
    tls: bool
    location: str
    grid: str | None  # valid Maidenhead only
    lat: float | None
    lon: float | None
    users: int
    users_max: int
    min_hz: int
    max_hz: int
    antenna: str
    snr_db: int | None


class NetSummary(_Model):
    """One recorded GhostNet window (GET /api/nets)."""

    id: str
    window_id: str
    label: str
    kind: Literal["net", "bridge"]
    band: str
    dial_hz: int
    scheduled_start: datetime
    scheduled_end: datetime
    started: datetime
    ended: datetime | None  # null while recording
    receiver: str | None
    receiver_reason: str
    decode_count: int
    station_count: int
    has_audio: bool
    has_waterfall: bool
    flash_count: int  # @GSTFLASH messages copied
    operator_override: bool  # a viewer retuned during the window


class NetLog(_Model):
    """A recorded net with its traffic (GET /api/nets/{id})."""

    summary: NetSummary
    decodes: list[Decode]
    stations: list[Station]
    waterfall_seconds: int  # rows in waterfall.png, one per second from `started`
    waterfall_offset_lo_hz: int
    waterfall_offset_hi_hz: int


class ReceiverDirectory(_Model):
    fetched_utc: datetime | None
    stale: bool  # served from cache after a failed refresh
    source: str
    receivers: list[ReceiverListing]


# ---------------------------------------------------------- client -> server


class ClientHello(_Msg):
    type: Literal["hello"] = "hello"
    client: str = Field(default="web", max_length=64)


class Tune(_Msg):
    type: Literal["tune"] = "tune"
    tuning: TuningModel


class SelectReceiver(_Msg):
    type: Literal["select_receiver"] = "select_receiver"
    receiver: ReceiverRef
    password: str = Field(default="", max_length=128)


class DisconnectReceiver(_Msg):
    type: Literal["disconnect_receiver"] = "disconnect_receiver"


class Subscribe(_Msg):
    """Opt in to binary channels. Both default off: no bytes the viewer does not want."""

    type: Literal["subscribe"] = "subscribe"
    audio: bool = False
    waterfall: bool = False


class Ping(_Msg):
    type: Literal["ping"] = "ping"


ClientMessage = Annotated[
    ClientHello | Tune | SelectReceiver | DisconnectReceiver | Subscribe | Ping,
    Field(discriminator="type"),
]
client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)

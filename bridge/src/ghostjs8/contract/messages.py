"""Bridge <-> browser protocol: the single source of truth.

JSON text frames are a discriminated union on ``type`` and carry the protocol
version ``v``. JSON Schema and TypeScript types are generated from these models
(``make contract``); never edit the generated files by hand.

Binary frames (audio, waterfall) are documented in docs/protocol.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ghostjs8 import PROTOCOL_VERSION


class _Msg(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    v: Literal[1] = PROTOCOL_VERSION


class Hello(_Msg):
    """First message on every connection."""

    type: Literal["hello"] = "hello"
    server: str = "ghost.js8"
    build: str


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
    grid: str | None = None


ServerMessage = Annotated[Hello | Decode, Field(discriminator="type")]
server_message_adapter: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)

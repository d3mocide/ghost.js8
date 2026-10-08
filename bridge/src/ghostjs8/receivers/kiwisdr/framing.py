"""KiwiSDR WebSocket framing. Pure functions; no I/O.

Every server message starts with a 3-byte ASCII tag. Layouts (verified against
jks-prv/kiwiclient and documented in docs/kiwisdr-notes.md):

    SND  tag(3) flags:u8 seq:u32le smeter:u16be  pcm...
    W/F  tag(3) pad:u8  x_bin:u32le flags_zoom:u32le seq:u32le  bins:u8...
    MSG  tag(3) pad:u8  "name=value name2=value2 ..." (values URL-encoded)
    EXT  tag(3) pad:u8  same as MSG

SND PCM is signed 16-bit **big-endian** unless SND_FLAG_LITTLE_ENDIAN is set.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from urllib.parse import unquote

from ghostjs8.receivers.base import (
    AudioFormatKind,
    MalformedFrame,
    ReceiverRejected,
    RejectReason,
    UnsupportedAudioFormat,
)

SND_FLAG_ADC_OVFL = 0x02
SND_FLAG_STEREO = 0x08
SND_FLAG_COMPRESSED = 0x10
SND_FLAG_LITTLE_ENDIAN = 0x80

SND_HEADER = struct.Struct("<BI")  # flags, seq
SND_SMETER = struct.Struct(">H")
SND_PREFIX_LEN = 3 + SND_HEADER.size + SND_SMETER.size  # 10
WF_HEADER = struct.Struct("<III")  # x_bin, flags_zoom, seq
WF_PREFIX_LEN = 3 + 1 + WF_HEADER.size  # 16

WF_BINS = 1024
WF_MAX_ZOOM = 14


@dataclass(frozen=True, slots=True)
class SndFrame:
    flags: int
    seq: int
    smeter: int
    data: bytes

    @property
    def rssi_dbm(self) -> float:
        return 0.1 * self.smeter - 127.0

    @property
    def adc_overload(self) -> bool:
        return bool(self.flags & SND_FLAG_ADC_OVFL)


@dataclass(frozen=True, slots=True)
class WfFrame:
    x_bin: int
    zoom: int
    flags: int
    seq: int
    bins: bytes


@dataclass(frozen=True, slots=True)
class MsgFrame:
    """MSG or EXT key/value list. Bare keys map to None. Order preserved."""

    tag: str
    params: tuple[tuple[str, str | None], ...]


Frame = SndFrame | WfFrame | MsgFrame


def parse_frame(raw: bytes | str) -> Frame | None:
    """Parse one server message. Unknown tags return None (ignored safely)."""
    data = raw.encode() if isinstance(raw, str) else raw
    if len(data) < 3:
        raise MalformedFrame(f"frame shorter than tag: {len(data)} bytes")
    tag = data[:3]
    if tag == b"SND":
        return _parse_snd(data)
    if tag == b"W/F":
        return _parse_wf(data)
    if tag in (b"MSG", b"EXT"):
        return MsgFrame(
            tag=tag.decode(), params=parse_msg_text(data[4:].decode("utf-8", "replace"))
        )
    return None


def _parse_snd(data: bytes) -> SndFrame:
    if len(data) < SND_PREFIX_LEN:
        raise MalformedFrame(f"SND frame truncated: {len(data)} bytes")
    flags, seq = SND_HEADER.unpack_from(data, 3)
    (smeter,) = SND_SMETER.unpack_from(data, 3 + SND_HEADER.size)
    return SndFrame(flags=flags, seq=seq, smeter=smeter, data=bytes(data[SND_PREFIX_LEN:]))


def _parse_wf(data: bytes) -> WfFrame:
    if len(data) < WF_PREFIX_LEN:
        raise MalformedFrame(f"W/F frame truncated: {len(data)} bytes")
    x_bin, flags_zoom, seq = WF_HEADER.unpack_from(data, 4)
    return WfFrame(
        x_bin=x_bin,
        zoom=flags_zoom & 0xFFFF,
        flags=(flags_zoom >> 16) & 0xFFFF,
        seq=seq,
        bins=bytes(data[WF_PREFIX_LEN:]),
    )


def parse_msg_text(text: str) -> tuple[tuple[str, str | None], ...]:
    out: list[tuple[str, str | None]] = []
    for token in text.strip().split(" "):
        if not token:
            continue
        name, sep, value = token.partition("=")
        out.append((name, unquote(value) if sep else None))
    return tuple(out)


# ---------------------------------------------------------------------------
# Audio normalization
# ---------------------------------------------------------------------------


def snd_to_s16le(frame: SndFrame, *, iq_mode: bool = False) -> bytes:
    """Return the frame's PCM as mono s16le, or raise a typed error.

    - compressed (ADPCM) frames are rejected: we request compression=0
    - stereo frames are rejected (IQ when the session requested IQ)
    - big-endian is the default and is byte-swapped
    - the little-endian flag is honored: no swap, never a double swap
    """
    if frame.flags & SND_FLAG_COMPRESSED:
        raise UnsupportedAudioFormat("compressed", "ADPCM audio; compression=0 was not honored")
    if frame.flags & SND_FLAG_STEREO:
        kind: AudioFormatKind = "iq" if iq_mode else "stereo"
        raise UnsupportedAudioFormat(kind, "2-channel audio")
    pcm = frame.data
    if len(pcm) % 2:
        raise MalformedFrame(f"odd PCM byte count {len(pcm)} in SND seq {frame.seq}")
    if frame.flags & SND_FLAG_LITTLE_ENDIAN:
        return pcm
    return swap16(pcm)


def swap16(pcm: bytes) -> bytes:
    """Swap byte order of each 16-bit word. Host-endianness independent."""
    out = bytearray(len(pcm))
    out[0::2] = pcm[1::2]
    out[1::2] = pcm[0::2]
    return bytes(out)


# ---------------------------------------------------------------------------
# Waterfall geometry
# ---------------------------------------------------------------------------


def wf_span_hz(zoom: int, bandwidth_hz: int) -> int:
    if not 0 <= zoom <= WF_MAX_ZOOM:
        raise ValueError(f"zoom out of range: {zoom}")
    return round(bandwidth_hz / (1 << zoom))


def wf_start_hz(x_bin: int, bandwidth_hz: int) -> int:
    """Start frequency of a row from the server's x_bin (full-resolution bins)."""
    return round(x_bin * bandwidth_hz / (WF_BINS << WF_MAX_ZOOM))


def wf_zoom_for_span(span_hz: int, bandwidth_hz: int) -> int:
    """Smallest zoom whose span still covers span_hz."""
    zoom = 0
    while zoom < WF_MAX_ZOOM and bandwidth_hz / (1 << (zoom + 1)) >= span_hz:
        zoom += 1
    return zoom


# ---------------------------------------------------------------------------
# Rejections
# ---------------------------------------------------------------------------

_BADP: dict[str, tuple[RejectReason, str]] = {
    "1": (RejectReason.AUTH, "bad password, or all channels not needing one are busy"),
    "2": (RejectReason.BUSY, "receiver still determining its local address"),
    "3": (RejectReason.AUTH, "admin connection not allowed from this address"),
    "4": (RejectReason.AUTH, "no admin password set"),
    "5": (RejectReason.DUPLICATE_IP, "no multiple connections from the same address"),
    "6": (RejectReason.BUSY, "database update in progress"),
    "7": (RejectReason.BUSY, "another admin connection is open"),
}


def rejection_from_msg(name: str, value: str | None) -> ReceiverRejected | None:
    """Map a MSG parameter to a typed rejection, or None if it is not one."""
    if name == "too_busy":
        return ReceiverRejected(RejectReason.FULL, f"all {value} client slots taken")
    if name == "badp":
        if value in (None, "0"):
            return None  # badp=0 means the password was accepted
        reason, detail = _BADP.get(value, (RejectReason.AUTH, f"badp={value}"))
        return ReceiverRejected(reason, detail)
    if name == "down":
        return ReceiverRejected(RejectReason.DOWN, "receiver reports it is down")
    if name == "redirect":
        return ReceiverRejected(RejectReason.REDIRECT, value or "")
    return None

"""Binary WebSocket frames, bridge -> browser. All integers little-endian.

    audio (0x01):     u8 channel | u8 flags | u16 reserved | u32 seq | u32 sample_rate | s16le PCM...
    waterfall (0x02): u8 channel | u8 flags | u16 bins     | u32 seq | u32 start_hz    | u32 span_hz | u8 bins...

audio flags:     bit0 = ADC overload reported by the receiver for this block
waterfall flags: reserved (0)

Mirrored in web/src/lib/protocol/binary.ts; docs/protocol.md is the spec.
"""

from __future__ import annotations

import struct

CHANNEL_AUDIO = 0x01
CHANNEL_WATERFALL = 0x02
AUDIO_FLAG_ADC_OVERLOAD = 0x01

AUDIO_HEADER = struct.Struct("<BBHII")
WATERFALL_HEADER = struct.Struct("<BBHIII")


def encode_audio(seq: int, sample_rate: int, pcm_s16le: bytes, *, adc_overload: bool) -> bytes:
    flags = AUDIO_FLAG_ADC_OVERLOAD if adc_overload else 0
    return AUDIO_HEADER.pack(CHANNEL_AUDIO, flags, 0, seq & 0xFFFFFFFF, sample_rate) + pcm_s16le


def encode_waterfall(seq: int, start_hz: int, span_hz: int, bins: bytes) -> bytes:
    return (
        WATERFALL_HEADER.pack(CHANNEL_WATERFALL, 0, len(bins), seq & 0xFFFFFFFF, start_hz, span_hz)
        + bins
    )

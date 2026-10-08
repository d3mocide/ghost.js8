import struct

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ghostjs8.receivers.base import (
    MalformedFrame,
    ReceiverRejected,
    RejectReason,
    UnsupportedAudioFormat,
)
from ghostjs8.receivers.kiwisdr import framing
from ghostjs8.receivers.kiwisdr.framing import (
    SND_FLAG_ADC_OVFL,
    SND_FLAG_COMPRESSED,
    SND_FLAG_LITTLE_ENDIAN,
    SND_FLAG_STEREO,
    MsgFrame,
    SndFrame,
    WfFrame,
    parse_frame,
    snd_to_s16le,
)


def snd(flags: int, pcm: bytes, seq: int = 7, smeter: int = 670) -> bytes:
    return b"SND" + struct.pack("<BI", flags, seq) + struct.pack(">H", smeter) + pcm


def be(*samples: int) -> bytes:
    return struct.pack(f">{len(samples)}h", *samples)


def le(*samples: int) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


# ----------------------------------------------------------------- parsing


def test_parse_snd_header_fields() -> None:
    frame = parse_frame(snd(SND_FLAG_ADC_OVFL, be(1, 2), seq=0x01020304, smeter=670))
    assert isinstance(frame, SndFrame)
    assert frame.seq == 0x01020304
    assert frame.smeter == 670
    assert frame.rssi_dbm == pytest.approx(-60.0)
    assert frame.adc_overload
    assert frame.data == be(1, 2)


def test_parse_wf_strips_16_byte_header() -> None:
    bins = bytes(range(256)) * 4
    raw = b"W/F\x00" + struct.pack("<III", 4096, (3 << 16) | 5, 99) + bins
    frame = parse_frame(raw)
    assert isinstance(frame, WfFrame)
    assert (frame.x_bin, frame.zoom, frame.flags, frame.seq) == (4096, 5, 3, 99)
    assert frame.bins == bins


def test_parse_msg_url_decodes_and_keeps_bare_keys() -> None:
    frame = parse_frame(b"MSG audio_rate=12000 wf_setup name=a%20b")
    assert frame == MsgFrame(
        tag="MSG", params=(("audio_rate", "12000"), ("wf_setup", None), ("name", "a b"))
    )


def test_parse_accepts_text_frames() -> None:
    assert isinstance(parse_frame("MSG down"), MsgFrame)


def test_unknown_tag_is_ignored() -> None:
    assert parse_frame(b"XYZ whatever") is None


@pytest.mark.parametrize(
    "raw",
    [b"", b"SN", b"SND\x00\x00", snd(0, b"")[:-1], b"W/F\x00" + b"\x00" * 11],
)
def test_truncated_frames_raise_malformed(raw: bytes) -> None:
    with pytest.raises(MalformedFrame):
        parse_frame(raw)


# ---------------------------------------------------------- normalization


def test_big_endian_is_default_and_swapped() -> None:
    frame = parse_frame(snd(0, be(1, -2, 0x1234)))
    assert isinstance(frame, SndFrame)
    assert snd_to_s16le(frame) == le(1, -2, 0x1234)


def test_little_endian_flag_is_honored_without_swap() -> None:
    frame = parse_frame(snd(SND_FLAG_LITTLE_ENDIAN, le(1, -2, 0x1234)))
    assert isinstance(frame, SndFrame)
    assert snd_to_s16le(frame) == le(1, -2, 0x1234)


@given(st.lists(st.integers(-32768, 32767), max_size=600))
def test_no_double_swap_property(samples: list[int]) -> None:
    from_be = snd_to_s16le(SndFrame(0, 0, 0, be(*samples)))
    from_le = snd_to_s16le(SndFrame(SND_FLAG_LITTLE_ENDIAN, 0, 0, le(*samples)))
    assert from_be == from_le == le(*samples)


def test_overload_flag_does_not_affect_byte_order() -> None:
    frame = SndFrame(SND_FLAG_ADC_OVFL, 0, 0, be(300))
    assert snd_to_s16le(frame) == le(300)


def test_compressed_frames_rejected() -> None:
    with pytest.raises(UnsupportedAudioFormat) as exc:
        snd_to_s16le(SndFrame(SND_FLAG_COMPRESSED, 0, 0, b"\x00\x00"))
    assert exc.value.kind == "compressed"


def test_stereo_frames_rejected() -> None:
    with pytest.raises(UnsupportedAudioFormat) as exc:
        snd_to_s16le(SndFrame(SND_FLAG_STEREO, 0, 0, b"\x00" * 14))
    assert exc.value.kind == "stereo"


def test_iq_frames_rejected_when_iq_mode() -> None:
    with pytest.raises(UnsupportedAudioFormat) as exc:
        snd_to_s16le(SndFrame(SND_FLAG_STEREO, 0, 0, b"\x00" * 14), iq_mode=True)
    assert exc.value.kind == "iq"


def test_odd_pcm_length_is_malformed() -> None:
    with pytest.raises(MalformedFrame):
        snd_to_s16le(SndFrame(0, 3, 0, b"\x00\x01\x02"))


# ---------------------------------------------------------------- geometry


def test_wf_geometry_full_band() -> None:
    assert framing.wf_span_hz(0, 30_000_000) == 30_000_000
    assert framing.wf_span_hz(14, 30_000_000) == 1831
    assert framing.wf_start_hz(0, 30_000_000) == 0
    full = framing.WF_BINS << framing.WF_MAX_ZOOM
    assert framing.wf_start_hz(full // 2, 30_000_000) == 15_000_000


@pytest.mark.parametrize(("span", "zoom"), [(30_000_000, 0), (12_000, 11), (3_000, 13), (1, 14)])
def test_zoom_for_span(span: int, zoom: int) -> None:
    z = framing.wf_zoom_for_span(span, 30_000_000)
    assert z == zoom
    assert framing.wf_span_hz(z, 30_000_000) >= min(span, framing.wf_span_hz(14, 30_000_000))


# --------------------------------------------------------------- rejections


@pytest.mark.parametrize(
    ("name", "value", "reason"),
    [
        ("too_busy", "4", RejectReason.FULL),
        ("badp", "1", RejectReason.AUTH),
        ("badp", "5", RejectReason.DUPLICATE_IP),
        ("badp", "6", RejectReason.BUSY),
        ("badp", "99", RejectReason.AUTH),
        ("down", None, RejectReason.DOWN),
        ("redirect", "http%3A//x", RejectReason.REDIRECT),
    ],
)
def test_rejections_are_typed(name: str, value: str | None, reason: RejectReason) -> None:
    rej = framing.rejection_from_msg(name, value)
    assert isinstance(rej, ReceiverRejected)
    assert rej.reason is reason


@pytest.mark.parametrize(
    ("name", "value"), [("badp", "0"), ("audio_rate", "12000"), ("wf_setup", None)]
)
def test_non_rejections(name: str, value: str | None) -> None:
    assert framing.rejection_from_msg(name, value) is None

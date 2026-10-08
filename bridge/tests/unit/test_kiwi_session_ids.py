import pytest

from ghostjs8.receivers.base import SessionPairingError, Tuning
from ghostjs8.receivers.kiwisdr.client import (
    KiwiEndpoint,
    passband_center_hz,
    passband_for,
    verify_pairing,
)


def test_stream_urls_share_session_id() -> None:
    ep = KiwiEndpoint("kiwi.example", 8073)
    snd, wf = ep.stream_url(1234, "SND"), ep.stream_url(1234, "W/F")
    assert snd == "ws://kiwi.example:8073/1234/SND"
    assert wf == "ws://kiwi.example:8073/1234/W/F"
    assert verify_pairing(snd, wf) == 1234


def test_mismatched_session_ids_fail() -> None:
    ep = KiwiEndpoint("kiwi.example")
    with pytest.raises(SessionPairingError):
        verify_pairing(ep.stream_url(1, "SND"), ep.stream_url(2, "W/F"))


def test_missing_session_id_fails() -> None:
    with pytest.raises(SessionPairingError):
        verify_pairing("ws://h:1/SND", "ws://h:1/W/F")


def test_tls_scheme() -> None:
    assert KiwiEndpoint("h", 443, tls=True).stream_url(5, "SND") == "wss://h:443/5/SND"


def test_usb_passband_positive() -> None:
    t = Tuning(dial_hz=14_078_000, mode="usb", low_cut_hz=100, high_cut_hz=3000)
    assert passband_for(t) == (100, 3000)
    assert passband_center_hz(t) == 14_079_550


def test_lsb_passband_mirrored_negative() -> None:
    t = Tuning(dial_hz=7_078_000, mode="lsb", low_cut_hz=100, high_cut_hz=3000)
    assert passband_for(t) == (-3000, -100)
    assert passband_center_hz(t) == 7_076_450


@pytest.mark.parametrize(
    "kwargs",
    [{"dial_hz": 0}, {"dial_hz": 14_078_000, "low_cut_hz": 3000, "high_cut_hz": 100}],
)
def test_bad_tuning_rejected(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError, match=r"\w"):
        Tuning(**kwargs)  # type: ignore[arg-type]

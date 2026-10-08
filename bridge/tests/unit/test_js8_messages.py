from datetime import UTC, datetime

import pytest

from ghostjs8.decoders.base import DecodeEvent, SpotEvent
from ghostjs8.decoders.js8call_native.messages import clean_text, parse_js8_message

NOW = datetime(2026, 10, 8, 2, 0, tzinfo=UTC)
UTC_MS = 1791424811558  # from a real JS8Call 3.0.3 datagram

# Shapes captured from JS8Call 3.0.3 decoding A_1_4.wav (docs/decoder-container.md).
ACTIVITY = {
    "type": "RX.ACTIVITY",
    "value": "K0OG: KN4CRD SNR +02 ",
    "params": {
        "_ID": -1,
        "DIAL": 14078000,
        "FREQ": 14078705,
        "OFFSET": 705,
        "SNR": -22,
        "SPEED": 0,
        "TDRIFT": 0.3,
        "UTC": UTC_MS,
        "BITS": 3,
    },
}
DIRECTED = {
    "type": "RX.DIRECTED",
    "value": "KN4CRD SNR +02 ♢ ",
    "params": {
        "_ID": -1,
        "FROM": "K0OG",
        "TO": "KN4CRD",
        "CMD": " SNR",
        "GRID": "",
        "EXTRA": "+02",
        "TEXT": "KN4CRD SNR +02 ♢ ",
        "DIAL": 14078000,
        "FREQ": 14078705,
        "OFFSET": 705,
        "SNR": -22,
        "SPEED": 0,
        "TDRIFT": 0.3,
        "UTC": UTC_MS,
    },
}


def one(msg: dict[str, object]) -> DecodeEvent | SpotEvent:
    events = parse_js8_message(msg, received_utc=NOW)
    assert len(events) == 1
    return events[0]


def test_activity() -> None:
    ev = one(ACTIVITY)
    assert isinstance(ev, DecodeEvent)
    assert ev.kind == "activity"
    assert ev.text == "K0OG: KN4CRD SNR +02"
    assert (ev.snr_db, ev.offset_hz, ev.speed, ev.from_call) == (-22, 705, "normal", "K0OG")
    assert ev.utc == datetime.fromtimestamp(UTC_MS / 1000, tz=UTC)


def test_directed_prefixes_sender_and_strips_eom() -> None:
    ev = one(DIRECTED)
    assert isinstance(ev, DecodeEvent)
    assert ev.kind == "directed"
    assert ev.text == "K0OG: KN4CRD SNR +02"
    assert (ev.from_call, ev.to_call, ev.grid) == ("K0OG", "KN4CRD", None)


def test_call_activity_yields_spots_with_grids() -> None:
    msg = {
        "type": "RX.CALL_ACTIVITY",
        "value": "",
        "params": {
            "_ID": 3,
            "K0OG": {"SNR": -22, "GRID": "EN34", "UTC": UTC_MS},
            "KG9B": {"SNR": -15, "GRID": "", "UTC": UTC_MS},
        },
    }
    spots = parse_js8_message(msg, received_utc=NOW)
    assert spots == [
        SpotEvent("K0OG", datetime.fromtimestamp(UTC_MS / 1000, tz=UTC), -22, None, "EN34"),
        SpotEvent("KG9B", datetime.fromtimestamp(UTC_MS / 1000, tz=UTC), -15, None, None),
    ]


def test_rx_spot_if_enabled() -> None:
    ev = one(
        {
            "type": "RX.SPOT",
            "value": "",
            "params": {"CALL": "K0OG", "SNR": -3, "GRID": "EN34", "OFFSET": 700},
        }
    )
    assert isinstance(ev, SpotEvent)
    assert (ev.callsign, ev.grid, ev.offset_hz, ev.utc) == ("K0OG", "EN34", 700, NOW)


@pytest.mark.parametrize(
    "msg",
    [
        {"type": "STATION.STATUS", "value": "", "params": {"OFFSET": 1500}},
        {"type": "PING", "value": "", "params": {"UTC": UTC_MS}},
        {"type": "TOTALLY.NEW", "value": "x", "params": {}},
        {"type": "RX.ACTIVITY", "value": "x", "params": {"SNR": "bad", "OFFSET": 1}},
        {"type": "RX.ACTIVITY", "value": "   ", "params": {"SNR": 1, "OFFSET": 1}},
        {"type": "RX.ACTIVITY", "value": "x", "params": "not a dict"},
        {"type": 5, "value": "x", "params": {}},
        {"value": "no type"},
        {"type": "RX.CALL_ACTIVITY", "value": "", "params": {"_ID": 1, "X": "not a dict"}},
    ],
)
def test_unknown_or_malformed_messages_are_ignored(msg: dict[str, object]) -> None:
    assert parse_js8_message(msg, received_utc=NOW) == []


def test_missing_utc_falls_back_to_receive_time() -> None:
    msg = {"type": "RX.ACTIVITY", "value": "A: B", "params": {"SNR": 1, "OFFSET": 2}}
    ev = one(msg)
    assert ev.utc == NOW


def test_speed_names() -> None:
    for code, name in ((1, "fast"), (2, "turbo"), (4, "slow"), (8, "ultra"), (99, "unknown")):
        params = {"SNR": 1, "OFFSET": 2, "SPEED": code}
        ev = one({"type": "RX.ACTIVITY", "value": "A: B", "params": params})
        assert isinstance(ev, DecodeEvent)
        assert ev.speed == name


def test_clean_text() -> None:
    assert clean_text("  HELLO ♢ ") == "HELLO"
    assert clean_text("HELLO") == "HELLO"

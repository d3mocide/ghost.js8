"""Normalize JS8Call UDP API messages into decoder events.

Message shape: ``{"type": str, "value": str, "params": {...}}``. Observed on
JS8Call 3.0.3 (see docs/decoder-container.md):

- ``RX.ACTIVITY``: ``value`` is the full line, e.g. ``"K0OG: KN4CRD SNR +02 "``.
- ``RX.DIRECTED``: ``value`` omits the sender (``params.FROM``) and ends with
  the end-of-message marker ``♢``. We display ``FROM: value`` like JS8Call does.
- ``RX.CALL_ACTIVITY``: reply to ``RX.GET_CALL_ACTIVITY``; ``params`` maps each
  heard callsign to ``{SNR, GRID, UTC}`` (plus ``_ID``). This is our station
  source: JS8Call only emits ``RX.SPOT`` when spotting to PSKReporter is on,
  which we keep off.
- ``RX.SPOT``: parsed if present (``params.CALL``), for completeness.

Unknown types and malformed payloads return None; they never raise.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ghostjs8.decoders.base import DecodeEvent, SpotEvent

EOM_MARKERS = ("♢",)  # JS8 end-of-message glyph appended to the last frame

SPEEDS = {0: "normal", 1: "fast", 2: "turbo", 4: "slow", 8: "ultra"}

FORWARDED_TYPES = frozenset({"RX.ACTIVITY", "RX.DIRECTED", "RX.SPOT", "RX.CALL_ACTIVITY"})


def clean_text(text: str) -> str:
    out = text.strip()
    for marker in EOM_MARKERS:
        out = out.removesuffix(marker).rstrip()
    return out


def _int(params: Mapping[str, Any], key: str) -> int | None:
    value = params.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value)
    return None


def _str(params: Mapping[str, Any], key: str) -> str | None:
    value = params.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _utc(params: Mapping[str, Any], fallback: datetime) -> datetime:
    ms = _int(params, "UTC")
    if ms is None or ms <= 0:
        return fallback
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def _speed(params: Mapping[str, Any]) -> str:
    sub = _int(params, "SPEED")
    return SPEEDS.get(sub, "unknown") if sub is not None else "unknown"


def _float(params: Mapping[str, Any], key: str) -> float | None:
    value = params.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def parse_js8_message(
    message: Mapping[str, Any], *, received_utc: datetime
) -> list[DecodeEvent | SpotEvent]:
    """Events carried by one JS8Call API message (often none)."""
    event = _parse_single(message, received_utc=received_utc)
    if event is not None:
        return [event]
    if message.get("type") == "RX.CALL_ACTIVITY":
        return list(_parse_call_activity(message, received_utc=received_utc))
    return []


def _parse_call_activity(
    message: Mapping[str, Any], *, received_utc: datetime
) -> list[DecodeEvent | SpotEvent]:
    params = message.get("params")
    if not isinstance(params, Mapping):
        return []
    out: list[DecodeEvent | SpotEvent] = []
    for call, detail in params.items():
        if not isinstance(call, str) or call.startswith("_") or not isinstance(detail, Mapping):
            continue
        callsign = call.strip()
        if not callsign:
            continue
        out.append(
            SpotEvent(
                callsign=callsign,
                utc=_utc(detail, received_utc),
                snr_db=_int(detail, "SNR"),
                grid=_str(detail, "GRID"),
            )
        )
    return out


def _parse_single(
    message: Mapping[str, Any], *, received_utc: datetime
) -> DecodeEvent | SpotEvent | None:
    mtype = message.get("type")
    value = message.get("value")
    params = message.get("params")
    if not isinstance(mtype, str) or not isinstance(params, Mapping):
        return None
    text = value if isinstance(value, str) else ""
    utc = _utc(params, received_utc)

    if mtype in ("RX.ACTIVITY", "RX.DIRECTED"):
        snr, offset = _int(params, "SNR"), _int(params, "OFFSET")
        if snr is None or offset is None:
            return None
        body = clean_text(text)
        if not body:
            return None
        if mtype == "RX.DIRECTED":
            sender = _str(params, "FROM")
            display = f"{sender}: {body}" if sender else body
            return DecodeEvent(
                kind="directed",
                utc=utc,
                text=display,
                snr_db=snr,
                offset_hz=offset,
                speed=_speed(params),
                from_call=sender,
                to_call=_str(params, "TO"),
                grid=_str(params, "GRID"),
                tdrift_s=_float(params, "TDRIFT"),
            )
        sender, sep, _ = body.partition(":")
        return DecodeEvent(
            kind="activity",
            utc=utc,
            text=body,
            snr_db=snr,
            offset_hz=offset,
            speed=_speed(params),
            from_call=sender.strip() if sep and " " not in sender.strip() else None,
            tdrift_s=_float(params, "TDRIFT"),
        )

    if mtype == "RX.SPOT":
        call = _str(params, "CALL") or _str(params, "CALLSIGN")
        if call is None:
            return None
        return SpotEvent(
            callsign=call,
            utc=utc,
            snr_db=_int(params, "SNR"),
            offset_hz=_int(params, "OFFSET"),
            grid=_str(params, "GRID"),
        )
    return None

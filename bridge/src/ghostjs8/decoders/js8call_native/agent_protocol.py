"""Bridge <-> decoder-agent wire protocol (internal network only).

One WebSocket at ``ws://<decoder>:8074/agent``.

bridge -> agent
    binary  mono s16le PCM at 12 kHz, any block size
    text    {"t": "hello", "bridge": "<version>"}

agent -> bridge (text, JSON)
    {"t": "js8", "rx_utc_ms": int, "msg": {<JS8Call API message, verbatim>}}
    {"t": "health", "utc_ms": int, "process_up": bool, "capturing": bool,
     "last_ping_utc_ms": int|null, "last_api_reply_utc_ms": int|null,
     "last_audio_write_utc_ms": int|null, "dropped_audio_blocks": int,
     "details": {str: str},
     "selftest": {"state": "unknown"|"ok"|"failed", "last_run_utc_ms": int|null,
                  "last_pass_utc_ms": int|null, "consecutive_failures": int,
                  "interval_s": float, "detail": str}}      (selftest optional)

bridge -> agent (text, JSON), besides ``hello``
    {"t": "selftest_hold", "hold": bool}   true while a GhostNet window is being recorded:
                                           the agent must not inject its self-test frame

The agent forwards JS8Call messages verbatim; normalization happens in the
bridge (``messages.py``) where it is unit-tested without a container.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from ghostjs8.decoders.base import DecoderHealth, SelfTestFacts

AGENT_PATH = "/agent"
DEFAULT_AGENT_PORT = 8074


def utc_ms(dt: datetime | None) -> int | None:
    return None if dt is None else round(dt.timestamp() * 1000)


def from_utc_ms(ms: object) -> datetime | None:
    if isinstance(ms, int) and not isinstance(ms, bool) and ms > 0:
        return datetime.fromtimestamp(ms / 1000, tz=UTC)
    return None


def encode_js8(message: dict[str, Any], received: datetime) -> str:
    return json.dumps({"t": "js8", "rx_utc_ms": utc_ms(received), "msg": message})


def encode_selftest_hold(hold: bool) -> str:
    return json.dumps({"t": "selftest_hold", "hold": hold})


def _encode_selftest(facts: SelfTestFacts | None) -> dict[str, Any] | None:
    if facts is None:
        return None
    return {
        "state": facts.state,
        "last_run_utc_ms": utc_ms(facts.last_run_utc),
        "last_pass_utc_ms": utc_ms(facts.last_pass_utc),
        "consecutive_failures": facts.consecutive_failures,
        "interval_s": facts.interval_s,
        "detail": facts.detail,
    }


def _decode_selftest(raw: object) -> SelfTestFacts | None:
    if not isinstance(raw, dict):
        return None
    state = raw.get("state")
    failures = raw.get("consecutive_failures")
    interval = raw.get("interval_s")
    detail = raw.get("detail")
    return SelfTestFacts(
        state=state if state in ("unknown", "ok", "failed") else "unknown",
        last_run_utc=from_utc_ms(raw.get("last_run_utc_ms")),
        last_pass_utc=from_utc_ms(raw.get("last_pass_utc_ms")),
        consecutive_failures=failures if isinstance(failures, int) else 0,
        interval_s=float(interval) if isinstance(interval, (int, float)) else 0.0,
        detail=detail if isinstance(detail, str) else "",
    )


def encode_health(health: DecoderHealth, now: datetime) -> str:
    return json.dumps(
        {
            "t": "health",
            "utc_ms": utc_ms(now),
            "process_up": health.process_up,
            "capturing": health.capturing,
            "last_ping_utc_ms": utc_ms(health.last_ping_utc),
            "last_api_reply_utc_ms": utc_ms(health.last_api_reply_utc),
            "last_audio_write_utc_ms": utc_ms(health.last_audio_write_utc),
            "dropped_audio_blocks": health.dropped_audio_blocks,
            "details": health.details,
            "selftest": _encode_selftest(health.selftest),
        }
    )


def decode_health(payload: dict[str, Any]) -> DecoderHealth:
    details = payload.get("details")
    dropped = payload.get("dropped_audio_blocks")
    return DecoderHealth(
        process_up=payload.get("process_up") is True,
        capturing=payload.get("capturing") is True,
        last_ping_utc=from_utc_ms(payload.get("last_ping_utc_ms")),
        last_api_reply_utc=from_utc_ms(payload.get("last_api_reply_utc_ms")),
        last_audio_write_utc=from_utc_ms(payload.get("last_audio_write_utc_ms")),
        dropped_audio_blocks=dropped if isinstance(dropped, int) else 0,
        details={str(k): str(v) for k, v in details.items()} if isinstance(details, dict) else {},
        selftest=_decode_selftest(payload.get("selftest")),
    )

"""Truthful readiness.

Every component state is derived from evidence with a timestamp, evaluated
against an injected clock. Nothing is inferred from an open socket, and the
last-decode time is only ever set by an actual decode.

Thresholds are deliberately generous enough for real receivers (network
jitter) and tight enough that a dead path shows within seconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ghostjs8.contract.messages import Component, Components, ComponentState, Health, SessionState
from ghostjs8.decoders.base import DecoderHealth
from ghostjs8.util.clock import Clock

_Eval = tuple[ComponentState, str, datetime | None]


@dataclass(frozen=True, slots=True)
class Thresholds:
    audio_stale_s: float = 3.0
    waterfall_stale_s: float = 5.0
    decoder_report_stale_s: float = 10.0  # agent sends health every 3 s
    decoder_ping_stale_s: float = 40.0  # JS8Call PINGs every 15 s


@dataclass(slots=True)
class _Tracked:
    state: ComponentState
    since: datetime


class HealthTracker:
    def __init__(self, clock: Clock, thresholds: Thresholds | None = None) -> None:
        self._clock = clock
        self._t = thresholds or Thresholds()
        self._started = clock.utc_now()
        self._tracked: dict[str, _Tracked] = {}
        self._decoder_link = False
        self._decoder_facts: DecoderHealth | None = None
        self._decoder_facts_mono: float | None = None
        self._decoder_facts_utc: datetime | None = None
        self._receiver_state: SessionState = "idle"
        self._receiver_detail = ""
        self._receiver_since_utc: datetime | None = None
        self._audio_mono: float | None = None
        self._audio_utc: datetime | None = None
        self._wf_mono: float | None = None
        self._wf_utc: datetime | None = None
        self._last_decode_utc: datetime | None = None
        self._last_snapshot: Health | None = None

    # -------------------------------------------------------------- inputs

    def decoder_link(self, connected: bool) -> None:
        self._decoder_link = connected
        if not connected:
            self._decoder_facts = None

    def decoder_facts(self, facts: DecoderHealth) -> None:
        self._decoder_facts = facts
        self._decoder_facts_mono = self._clock.monotonic()
        self._decoder_facts_utc = self._clock.utc_now()

    def receiver(self, state: SessionState, detail: str = "") -> None:
        if state != self._receiver_state:
            self._receiver_since_utc = self._clock.utc_now()
        self._receiver_state = state
        self._receiver_detail = detail
        if state != "connected":
            self._audio_mono = self._wf_mono = None

    def audio(self) -> None:
        self._audio_mono = self._clock.monotonic()
        self._audio_utc = self._clock.utc_now()

    def waterfall(self) -> None:
        self._wf_mono = self._clock.monotonic()
        self._wf_utc = self._clock.utc_now()

    def decoded(self, utc: datetime) -> None:
        if self._last_decode_utc is None or utc > self._last_decode_utc:
            self._last_decode_utc = utc

    # ------------------------------------------------------------- outputs

    def snapshot(self) -> Health:
        now = self._clock.utc_now()
        proc = self._decoder_process()
        decoder_up = proc[0] == "ok"
        api = self._decoder_api(now) if decoder_up else ("down", "decoder process down", None)
        cap = self._decoder_capture() if decoder_up else ("down", "decoder process down", None)
        rx = self._receiver()
        rx_up = self._receiver_state == "connected"
        audio = self._stream(
            self._audio_mono, self._audio_utc, self._t.audio_stale_s, "audio", rx_up
        )
        wf = self._stream(
            self._wf_mono, self._wf_utc, self._t.waterfall_stale_s, "waterfall", rx_up
        )

        components = Components(
            bridge=self._component("bridge", ("ok", "", now), now),
            decoder_process=self._component("decoder_process", proc, now),
            decoder_api=self._component("decoder_api", api, now),
            decoder_capture=self._component("decoder_capture", cap, now),
            receiver=self._component("receiver", rx, now),
            audio=self._component("audio", audio, now),
            waterfall=self._component("waterfall", wf, now),
        )
        decode_path = (proc, api, cap, rx, audio)
        overall: Literal["listening", "degraded", "offline"]
        if all(c[0] == "ok" for c in decode_path):
            overall = "listening"
        elif not decoder_up or not rx_up:
            overall = "offline"
        else:
            overall = "degraded"
        snap = Health(
            utc=now, overall=overall, components=components, last_decode_utc=self._last_decode_utc
        )
        self._last_snapshot = snap
        return snap

    def poll(self) -> tuple[Health, bool]:
        """Snapshot plus whether any state (or the last decode) changed since the previous one."""
        prev = self._last_snapshot
        current = self.snapshot()
        changed = (
            prev is None
            or _states(prev) != _states(current)
            or prev.last_decode_utc != current.last_decode_utc
        )
        return current, changed

    # ---------------------------------------------------------- evaluation

    def _component(self, name: str, ev: _Eval, now: datetime) -> Component:
        state, detail, last_seen = ev
        tracked = self._tracked.get(name)
        if tracked is None or tracked.state != state:
            tracked = _Tracked(state, now if tracked is not None else self._started)
            self._tracked[name] = tracked
        return Component(state=state, since=tracked.since, last_seen=last_seen, detail=detail)

    def _decoder_process(self) -> _Eval:
        if not self._decoder_link:
            return ("down", "decoder agent unreachable", self._decoder_facts_utc)
        facts = self._decoder_facts
        if facts is None or self._decoder_facts_mono is None:
            return ("unknown", "waiting for decoder report", None)
        age = self._clock.monotonic() - self._decoder_facts_mono
        if age > self._t.decoder_report_stale_s:
            return ("down", f"no decoder report for {age:.0f}s", self._decoder_facts_utc)
        if not facts.process_up:
            return ("down", "JS8Call process not running", self._decoder_facts_utc)
        return ("ok", "", self._decoder_facts_utc)

    def _decoder_api(self, now: datetime) -> _Eval:
        facts = self._decoder_facts
        if facts is None:
            return ("unknown", "", None)
        seen = _latest(facts.last_ping_utc, facts.last_api_reply_utc)
        if seen is None:
            return ("down", "no API heartbeat yet", None)
        age = (now - seen).total_seconds()
        if age > self._t.decoder_ping_stale_s:
            return ("down", f"no API heartbeat for {age:.0f}s", seen)
        return ("ok", "", seen)

    def _decoder_capture(self) -> _Eval:
        facts = self._decoder_facts
        if facts is None:
            return ("unknown", "", None)
        if not facts.capturing:
            return ("down", "decoder is not capturing its audio input", facts.last_audio_write_utc)
        return ("ok", "", facts.last_audio_write_utc)

    def _receiver(self) -> _Eval:
        state, detail = self._receiver_state, self._receiver_detail
        since = self._receiver_since_utc
        if state == "connected":
            return ("ok", detail, self._audio_utc or since)
        if state in ("connecting", "backoff"):
            return ("degraded", detail or state, since)
        if state == "idle":
            return ("unknown", detail or "no receiver selected", None)
        return ("down", detail or state, since)

    def _stream(
        self, mono: float | None, utc: datetime | None, stale_s: float, what: str, rx_up: bool
    ) -> _Eval:
        if not rx_up:
            return ("unknown", "receiver not connected", utc)
        if mono is None:
            return ("down", f"no {what} yet", None)
        age = self._clock.monotonic() - mono
        if age > stale_s:
            return ("down", f"{what} stale for {age:.0f}s", utc)
        return ("ok", "", utc)


def _latest(*times: datetime | None) -> datetime | None:
    present = [t for t in times if t is not None]
    return max(present) if present else None


def _states(h: Health) -> tuple[str, ...]:
    c = h.components
    return (
        h.overall,
        c.bridge.state,
        c.decoder_process.state,
        c.decoder_api.state,
        c.decoder_capture.state,
        c.receiver.state,
        c.audio.state,
        c.waterfall.state,
    )

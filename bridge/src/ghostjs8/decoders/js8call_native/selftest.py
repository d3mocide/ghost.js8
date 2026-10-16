"""Known-answer decode self-test for the native JS8Call decoder.

``decoder_process`` / ``decoder_api`` / ``decoder_capture`` only prove that
JS8Call is alive and listening. They say nothing about whether it still decodes.
This module closes that gap: once an interval the agent mixes a short recording
of a real, previously decoded JS8 transmission into the audio it feeds JS8Call
(at a UTC 15 s boundary, after the bridge has already fanned the audio out to
browsers, so no viewer ever hears it) and checks that the expected text comes back.

- The clip is a 15 s slice of one of our own GhostNet recordings (see
  ``docs/decoder-selftest.md``). ``CANARY_FRAMES`` is what a healthy JS8Call
  decodes from it.
- Canary decodes never leave the agent: ``SelfTest.intercept`` swallows them, along
  with JS8Call's delayed ``……`` re-report, and strips the canary callsign from
  the polled call-activity list. Nothing reaches the store, the UI or the heard list.
- Failures are counted. Two in a row restart JS8Call (with a cooldown). A single
  failure may only be a real signal sitting on a canary offset.
- The bridge can hold the test (``selftest_hold``) while a GhostNet window records.

Everything time-dependent uses an injected ``Clock``.
"""

from __future__ import annotations

import logging
import math
import os
import wave
from array import array
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from ghostjs8.decoders.base import SelfTestFacts, SelfTestState
from ghostjs8.decoders.js8call_native.messages import clean_text
from ghostjs8.util.clock import Clock

log = logging.getLogger("ghostjs8.agent.selftest")

SAMPLE_RATE_HZ = 12_000
PERIOD_S = 15
OFFSET_TOLERANCE_HZ = 8  # JS8Call's reported offset wobbles by a few Hz after mixing
SUPPRESS_S = 90.0  # decode (~13 s) plus JS8Call's delayed re-report (~35 s later) fit well inside
DEADLINE_S = 35.0  # a healthy decoder reports the strong frames about 14 s after injection
START_LEAD_S = 2.0  # arm at least this far ahead of the next period boundary
ELLIPSIS = "…"


@dataclass(frozen=True, slots=True)
class CanaryFrame:
    offset_hz: int
    text: str
    counts: bool  # a pass needs at least one frame that counts; weak frames only get suppressed

    @property
    def callsign(self) -> str | None:
        head, sep, _ = self.text.partition(":")
        return head if sep and head and " " not in head and not head.startswith("@") else None


# What JS8Call 3.0.3 decodes from selftest/canary-js8-normal.wav in a fresh container
# (GhostNet North America, 2026-10-16 01:01:15Z; SNR as measured alone, lower once mixed).
CANARY_FRAMES: tuple[CanaryFrame, ...] = (
    CanaryFrame(1022, "@GHOSTNET", counts=True),  # +7 dB
    CanaryFrame(2321, "KB8JEP:", counts=True),  # -4 dB
    CanaryFrame(1343, "FOR NET.", counts=False),  # -20 dB: too weak to rely on
)


class Action(Enum):
    NONE = "none"
    RESTART_DECODER = "restart-decoder"


def load_clip(path: str) -> bytes:
    """Mono s16le 12 kHz PCM from a WAV file. Raises ValueError for anything else."""
    try:
        with wave.open(path, "rb") as w:
            if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, SAMPLE_RATE_HZ):
                raise ValueError("self-test clip must be mono 16-bit 12 kHz")
            pcm = w.readframes(w.getnframes())
    except (OSError, wave.Error, EOFError) as exc:
        raise ValueError(f"cannot read self-test clip {path}: {exc}") from exc
    if len(pcm) != PERIOD_S * SAMPLE_RATE_HZ * 2:
        raise ValueError(f"self-test clip must be exactly {PERIOD_S} s")
    return pcm


def next_boundary(now: datetime, lead_s: float = START_LEAD_S) -> datetime:
    """The first UTC period boundary at least ``lead_s`` from now."""
    ts = math.ceil((now.timestamp() + lead_s) / PERIOD_S) * PERIOD_S
    return datetime.fromtimestamp(ts, tz=UTC)


class CanaryMixer:
    """Adds the clip into the PCM stream starting at an armed UTC instant."""

    def __init__(self, clip_pcm: bytes) -> None:
        self._clip = array("h")
        self._clip.frombytes(clip_pcm)
        self._armed_at: datetime | None = None
        self._pos: int | None = None

    @property
    def active(self) -> bool:
        return self._armed_at is not None

    def arm(self, start: datetime) -> None:
        self._armed_at = start
        self._pos = None

    def cancel(self) -> None:
        self._armed_at = None
        self._pos = None

    def mix(self, block: bytes, now: datetime) -> bytes:
        """``block`` is s16le mono. Returns it unchanged unless the clip is playing."""
        if self._armed_at is None or len(block) < 2:
            return block
        if self._pos is None:
            if now < self._armed_at:
                return block
            self._pos = 0
        samples = array("h")
        samples.frombytes(block[: len(block) // 2 * 2])
        n = min(len(samples), len(self._clip) - self._pos)
        for i in range(n):
            mixed = samples[i] + self._clip[self._pos + i]
            samples[i] = max(-32768, min(32767, mixed))
        self._pos += n
        if self._pos >= len(self._clip):
            self.cancel()
        return samples.tobytes() + block[len(samples) * 2 :]


def _is_ellipsis_only(text: str) -> bool:
    return bool(text) and set(text) <= {ELLIPSIS, " ", "."}


class SelfTest:
    """Schedules the test, recognises its decodes, and reports ``SelfTestFacts``."""

    def __init__(
        self,
        clock: Clock,
        mixer: CanaryMixer,
        *,
        frames: tuple[CanaryFrame, ...] = CANARY_FRAMES,
        interval_s: float = 3600.0,
        first_delay_s: float = 300.0,
        retry_s: float = 120.0,
        restart_after: int = 2,
        restart_cooldown_s: float = 1800.0,
        post_restart_delay_s: float = 120.0,
        defer_s: float = 30.0,
        load: Callable[[], float] | None = None,
    ) -> None:
        self._clock = clock
        self._mixer = mixer
        self._frames = frames
        self._interval_s = interval_s
        self._retry_s = retry_s
        self._restart_after = restart_after
        self._restart_cooldown = timedelta(seconds=restart_cooldown_s)
        self._post_restart_delay_s = post_restart_delay_s
        self._defer_s = defer_s
        self._load = load or _load1
        now = clock.utc_now()
        self._next_run = now + timedelta(seconds=first_delay_s)
        self._running_since: datetime | None = None
        self._start: datetime | None = None
        self._seen: set[str] = set()
        self._windows: deque[tuple[datetime, datetime]] = deque(maxlen=64)
        self._cooldown_until = now
        self._state: SelfTestState = "unknown"
        self._last_run: datetime | None = None
        self._last_pass: datetime | None = None
        self._failures = 0
        self._detail = "no self-test has run yet"

    # ------------------------------------------------------------ reporting

    def facts(self) -> SelfTestFacts:
        return SelfTestFacts(
            state=self._state,
            last_run_utc=self._last_run,
            last_pass_utc=self._last_pass,
            consecutive_failures=self._failures,
            interval_s=self._interval_s,
            detail=self._detail,
        )

    @property
    def running(self) -> bool:
        return self._start is not None

    def mix(self, block: bytes, now: datetime) -> bytes:
        """Audio on its way to JS8Call: the canary is added while a test is injecting."""
        return self._mixer.mix(block, now)

    # ------------------------------------------------------- decode filtering

    def intercept(self, message: dict[str, Any], now: datetime) -> bool:
        """True if ``message`` is canary traffic that must not be forwarded.

        Also scrubs the canary callsign out of ``RX.CALL_ACTIVITY`` in place.
        """
        mtype = message.get("type")
        if mtype == "RX.CALL_ACTIVITY":
            self._scrub_call_activity(message)
            return False
        if mtype not in ("RX.ACTIVITY", "RX.DIRECTED") or not self._in_window(now):
            return False
        params = message.get("params")
        value = message.get("value")
        offset = params.get("OFFSET") if isinstance(params, Mapping) else None
        if isinstance(offset, bool) or not isinstance(offset, (int, float)):
            return False
        text = clean_text(value) if isinstance(value, str) else ""
        near = [f for f in self._frames if abs(f.offset_hz - offset) <= OFFSET_TOLERANCE_HZ]
        if not near:
            return False
        if _is_ellipsis_only(text):
            return True  # JS8Call's delayed re-report of a canary frame
        for frame in near:
            if text == frame.text:
                if mtype == "RX.ACTIVITY" and frame.counts and self.running:
                    self._seen.add(frame.text)
                return True
        return False

    def _in_window(self, now: datetime) -> bool:
        return any(start <= now <= end for start, end in self._windows)

    def _scrub_call_activity(self, message: dict[str, Any]) -> None:
        params = message.get("params")
        if not isinstance(params, dict):
            return
        for call in {f.callsign for f in self._frames if f.callsign}:
            detail = params.get(call)
            ms = detail.get("UTC") if isinstance(detail, Mapping) else None
            if isinstance(ms, bool) or not isinstance(ms, (int, float)) or ms <= 0:
                continue
            heard = datetime.fromtimestamp(ms / 1000, tz=UTC)
            if self._in_window(heard):
                del params[call]

    # ----------------------------------------------------------- scheduling

    def step(self, *, ready: bool, hold: bool) -> Action:
        """Advance the state machine. Call about once a second."""
        now = self._clock.utc_now()
        if self._start is not None:
            return self._poll_running(now)
        if now < self._next_run:
            return Action.NONE
        if hold or not ready:
            self._next_run = now + timedelta(seconds=self._defer_s)
            return Action.NONE
        self._begin(now)
        return Action.NONE

    def _begin(self, now: datetime) -> None:
        start = next_boundary(now)
        self._start = start
        self._seen = set()
        self._windows.append((start, start + timedelta(seconds=SUPPRESS_S)))
        self._mixer.arm(start)
        log.info("self-test: injecting canary at %s", start.strftime("%H:%M:%S"))

    def _poll_running(self, now: datetime) -> Action:
        assert self._start is not None  # noqa: S101 - guarded by the caller
        if self._seen:
            return self._finish(now, passed=True)
        if now < self._start + timedelta(seconds=DEADLINE_S):
            return Action.NONE
        return self._finish(now, passed=False)

    def _finish(self, now: datetime, *, passed: bool) -> Action:
        self._mixer.cancel()
        self._last_run = now
        self._start = None
        load = self._load()
        if passed:
            self._state, self._failures = "ok", 0
            self._last_pass = now
            self._detail = f"decoded {', '.join(sorted(self._seen))} (load {load:.1f})"
            self._next_run = now + timedelta(seconds=self._interval_s)
            log.info("self-test passed: %s", self._detail)
            return Action.NONE
        self._state = "failed"
        self._failures += 1
        self._detail = f"no canary decode within {DEADLINE_S:.0f} s (load {load:.1f})"
        log.warning("self-test failed (%d in a row): %s", self._failures, self._detail)
        if self._failures >= self._restart_after and now >= self._cooldown_until:
            self._cooldown_until = now + self._restart_cooldown
            self._next_run = now + timedelta(seconds=self._post_restart_delay_s)
            self._detail += "; JS8Call restarted"
            return Action.RESTART_DECODER
        self._next_run = now + timedelta(seconds=self._retry_s)
        return Action.NONE


def _load1() -> float:
    try:
        return os.getloadavg()[0]
    except OSError:  # pragma: no cover - platform without getloadavg
        return 0.0

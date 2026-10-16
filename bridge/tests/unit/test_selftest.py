from __future__ import annotations

import wave
from array import array
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from ghostjs8.decoders.js8call_native.selftest import (
    CANARY_FRAMES,
    DEADLINE_S,
    SAMPLE_RATE_HZ,
    Action,
    CanaryMixer,
    SelfTest,
    load_clip,
    next_boundary,
)
from ghostjs8.util.clock import ManualClock

CLIP_SAMPLES = 15 * SAMPLE_RATE_HZ
SHIPPED_CLIP = (
    Path(__file__).resolve().parents[3]
    / "decoder/rootfs/usr/share/ghostjs8/selftest/canary-js8-normal.wav"
)


def pcm(value: int, n: int) -> bytes:
    return array("h", [value] * n).tobytes()


def samples(data: bytes) -> list[int]:
    a = array("h")
    a.frombytes(data)
    return list(a)


def make(clock: ManualClock, **kw: Any) -> tuple[SelfTest, CanaryMixer]:
    mixer = CanaryMixer(pcm(100, CLIP_SAMPLES))
    kw.setdefault("load", lambda: 1.5)
    kw.setdefault("first_delay_s", 0)
    return SelfTest(clock, mixer, **kw), mixer


def start_clock() -> ManualClock:
    return ManualClock(datetime(2026, 1, 1, 0, 0, 3, tzinfo=UTC))


def activity(offset: int, text: str, *, kind: str = "RX.ACTIVITY") -> dict[str, Any]:
    return {"type": kind, "value": text, "params": {"OFFSET": offset, "SNR": -2}}


# ----------------------------------------------------------------- the clip


def test_shipped_clip_is_a_15s_mono_12k_wav() -> None:
    assert len(load_clip(str(SHIPPED_CLIP))) == CLIP_SAMPLES * 2


def test_load_clip_rejects_the_wrong_format(tmp_path: Path) -> None:
    bad = tmp_path / "bad.wav"
    with wave.open(str(bad), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE_HZ)
        w.writeframes(b"\x00\x00" * 100)
    with pytest.raises(ValueError, match="mono 16-bit 12 kHz"):
        load_clip(str(bad))
    with pytest.raises(ValueError, match="cannot read"):
        load_clip(str(tmp_path / "missing.wav"))


# ------------------------------------------------------------------- mixer


def test_next_boundary_is_aligned_and_leaves_lead_time() -> None:
    now = datetime(2026, 1, 1, 0, 0, 14, tzinfo=UTC)
    assert next_boundary(now) == datetime(2026, 1, 1, 0, 0, 30, tzinfo=UTC)
    now = datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC)
    assert next_boundary(now) == datetime(2026, 1, 1, 0, 0, 15, tzinfo=UTC)


def test_mixer_is_transparent_until_armed_and_started() -> None:
    mixer = CanaryMixer(pcm(100, CLIP_SAMPLES))
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    block = pcm(1000, 512)
    assert mixer.mix(block, t0) == block  # not armed
    mixer.arm(t0 + timedelta(seconds=15))
    assert mixer.mix(block, t0) == block  # armed, start not reached
    assert samples(mixer.mix(block, t0 + timedelta(seconds=15)))[:2] == [1100, 1100]


def test_mixer_plays_exactly_one_clip_across_blocks_then_stops() -> None:
    mixer = CanaryMixer(pcm(100, CLIP_SAMPLES))
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    mixer.arm(t0)
    mixed = 0
    for _ in range(0, CLIP_SAMPLES + 2048, 500):  # 500-sample blocks, not a divisor of the clip
        out = samples(mixer.mix(pcm(1000, 500), t0))
        mixed += sum(1 for v in out if v == 1100)
    assert mixed == CLIP_SAMPLES
    assert not mixer.active
    assert mixer.mix(pcm(1000, 4), t0) == pcm(1000, 4)


def test_mixer_clips_instead_of_wrapping() -> None:
    mixer = CanaryMixer(pcm(20000, CLIP_SAMPLES))
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    mixer.arm(t0)
    assert samples(mixer.mix(pcm(20000, 4), t0)) == [32767] * 4
    assert samples(CanaryMixer(pcm(-20000, CLIP_SAMPLES)).mix(pcm(-20000, 4), t0)) == [-20000] * 4
    low = CanaryMixer(pcm(-20000, CLIP_SAMPLES))
    low.arm(t0)
    assert samples(low.mix(pcm(-20000, 4), t0)) == [-32768] * 4


def test_mixer_keeps_an_odd_trailing_byte() -> None:
    mixer = CanaryMixer(pcm(100, CLIP_SAMPLES))
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    mixer.arm(t0)
    out = mixer.mix(pcm(1000, 2) + b"\x07", t0)
    assert len(out) == 5
    assert out[-1] == 7


# ------------------------------------------------------------- state machine


def test_first_run_waits_for_the_first_delay_and_reports_unknown_before_it() -> None:
    clock = start_clock()
    st, mixer = make(clock, first_delay_s=300)
    assert st.facts().state == "unknown"
    clock.advance(299)
    st.step(ready=True, hold=False)
    assert not st.running
    clock.advance(2)
    st.step(ready=True, hold=False)
    assert st.running
    assert mixer.active


def test_pass_records_ok_and_schedules_the_next_run_an_interval_out() -> None:
    clock = start_clock()
    st, mixer = make(clock, interval_s=3600)
    st.step(ready=True, hold=False)
    clock.advance(
        18
    )  # past the armed boundary (at most ~17 s out)  # past the 00:00:15 boundary armed at +2 s lead
    assert st.intercept(activity(1023, "@GHOSTNET"), clock.utc_now()) is True
    assert st.step(ready=True, hold=False) is Action.NONE
    facts = st.facts()
    assert (facts.state, facts.consecutive_failures) == ("ok", 0)
    assert facts.last_pass_utc == clock.utc_now()
    assert "@GHOSTNET" in facts.detail
    assert not mixer.active
    clock.advance(3599)
    st.step(ready=True, hold=False)
    assert not st.running
    clock.advance(2)
    st.step(ready=True, hold=False)
    assert st.running


def test_the_secondary_strong_frame_also_passes() -> None:
    clock = start_clock()
    st, _ = make(clock)
    st.step(ready=True, hold=False)
    clock.advance(18)  # past the armed boundary (at most ~17 s out)
    assert st.intercept(activity(2319, "KB8JEP:"), clock.utc_now()) is True
    st.step(ready=True, hold=False)
    assert st.facts().state == "ok"


def test_the_weak_frame_is_swallowed_but_does_not_pass() -> None:
    clock = start_clock()
    st, _ = make(clock)
    st.step(ready=True, hold=False)
    clock.advance(18)  # past the armed boundary (at most ~17 s out)
    assert st.intercept(activity(1343, "FOR NET."), clock.utc_now()) is True
    st.step(ready=True, hold=False)
    assert st.running  # still waiting for a strong frame


def test_failure_retries_soon_and_two_in_a_row_restart_the_decoder() -> None:
    clock = start_clock()
    st, _ = make(clock, retry_s=120, restart_after=2)
    st.step(ready=True, hold=False)
    clock.advance(15 + DEADLINE_S + 1)  # armed boundary is at most ~17 s out
    assert st.step(ready=True, hold=False) is Action.NONE
    facts = st.facts()
    assert (facts.state, facts.consecutive_failures) == ("failed", 1)
    assert "load 1.5" in facts.detail
    clock.advance(119)
    st.step(ready=True, hold=False)
    assert not st.running  # retry not due yet
    clock.advance(2)
    st.step(ready=True, hold=False)
    assert st.running
    clock.advance(15 + DEADLINE_S + 1)  # armed boundary is at most ~17 s out
    assert st.step(ready=True, hold=False) is Action.RESTART_DECODER
    assert st.facts().consecutive_failures == 2


def test_restart_has_a_cooldown_and_a_pass_resets_the_count() -> None:
    clock = start_clock()
    st, _ = make(
        clock, retry_s=10, restart_after=1, restart_cooldown_s=1800, post_restart_delay_s=10
    )
    actions = []
    for _ in range(3):
        clock.advance(11)
        st.step(ready=True, hold=False)
        clock.advance(15 + DEADLINE_S + 1)  # armed boundary is at most ~17 s out
        actions.append(st.step(ready=True, hold=False))
    assert actions == [Action.RESTART_DECODER, Action.NONE, Action.NONE]  # cooldown holds
    clock.advance(11)
    st.step(ready=True, hold=False)
    clock.advance(18)  # past the armed boundary (at most ~17 s out)
    st.intercept(activity(1022, "@GHOSTNET"), clock.utc_now())
    st.step(ready=True, hold=False)
    assert st.facts().consecutive_failures == 0


def test_hold_or_not_ready_defers_without_counting_a_failure() -> None:
    clock = start_clock()
    st, mixer = make(clock, defer_s=30)
    assert st.step(ready=True, hold=True) is Action.NONE
    assert not st.running
    assert not mixer.active
    clock.advance(31)
    st.step(ready=False, hold=False)
    assert not st.running
    clock.advance(31)
    st.step(ready=True, hold=False)
    assert st.running
    assert st.facts().consecutive_failures == 0


# ---------------------------------------------------------------- filtering


def test_canary_decodes_and_the_late_ellipsis_rereport_are_swallowed() -> None:
    clock = start_clock()
    st, _ = make(clock)
    st.step(ready=True, hold=False)
    clock.advance(18)  # past the armed boundary (at most ~17 s out)
    now = clock.utc_now()
    assert st.intercept(activity(1022, "@GHOSTNET"), now) is True
    assert st.intercept(activity(2321, "KB8JEP:"), now) is True
    clock.advance(34)  # JS8Call re-reports the same frame about 35 s later
    assert st.intercept(activity(1022, "……"), clock.utc_now()) is True
    assert st.intercept(activity(2321, "…"), clock.utc_now()) is True


def test_real_traffic_is_never_swallowed() -> None:
    clock = start_clock()
    st, _ = make(clock)
    now = clock.utc_now()
    # before any test: even a perfect match is real
    assert st.intercept(activity(1022, "@GHOSTNET"), now) is False
    st.step(ready=True, hold=False)
    clock.advance(18)  # past the armed boundary (at most ~17 s out)
    now = clock.utc_now()
    assert st.intercept(activity(1022, "CK IN NW ARK."), now) is False  # right offset, other text
    assert st.intercept(activity(1500, "@GHOSTNET"), now) is False  # right text, other offset
    assert st.intercept(activity(1500, "……"), now) is False
    assert st.intercept(activity(1022, "@GHOSTNET", kind="STATION.STATUS"), now) is False
    clock.advance(200)  # long after the window
    assert st.intercept(activity(1022, "@GHOSTNET"), clock.utc_now()) is False


def test_malformed_messages_are_ignored() -> None:
    clock = start_clock()
    st, _ = make(clock)
    st.step(ready=True, hold=False)
    clock.advance(18)  # past the armed boundary (at most ~17 s out)
    now = clock.utc_now()
    for msg in (
        {"type": "RX.ACTIVITY", "value": "@GHOSTNET"},
        {"type": "RX.ACTIVITY", "value": "@GHOSTNET", "params": {"OFFSET": True}},
        {"type": "RX.ACTIVITY", "value": None, "params": {"OFFSET": 1022}},
        {"type": "RX.CALL_ACTIVITY", "params": "nope"},
    ):
        assert st.intercept(msg, now) is False


def test_canary_callsign_is_scrubbed_from_call_activity_only_when_heard_in_a_window() -> None:
    clock = start_clock()
    st, _ = make(clock)
    st.step(ready=True, hold=False)
    clock.advance(18)  # past the armed boundary (at most ~17 s out)
    heard_in_window = int(clock.utc_now().timestamp() * 1000)
    clock.advance(500)
    heard_for_real = int(clock.utc_now().timestamp() * 1000)

    canary = {
        "type": "RX.CALL_ACTIVITY",
        "params": {"KB8JEP": {"UTC": heard_in_window, "SNR": -4}, "W1AW": {"UTC": heard_in_window}},
    }
    assert st.intercept(canary, clock.utc_now()) is False  # forwarded, but scrubbed
    assert list(canary["params"]) == ["W1AW"]

    real = {"type": "RX.CALL_ACTIVITY", "params": {"KB8JEP": {"UTC": heard_for_real, "SNR": -9}}}
    st.intercept(real, clock.utc_now())
    assert list(real["params"]) == ["KB8JEP"]  # a genuine hearing outside the window stays


def test_canary_frames_match_the_documented_clip() -> None:
    assert [(f.offset_hz, f.text) for f in CANARY_FRAMES if f.counts] == [
        (1022, "@GHOSTNET"),
        (2321, "KB8JEP:"),
    ]
    assert [f.callsign for f in CANARY_FRAMES] == [None, "KB8JEP", None]

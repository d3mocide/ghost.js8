from datetime import timedelta

from ghostjs8.decoders.base import DecoderHealth
from ghostjs8.session.health import HealthTracker
from ghostjs8.util.clock import ManualClock


def facts(
    clock: ManualClock, *, up: bool = True, capturing: bool = True, ping_age: float = 1.0
) -> DecoderHealth:
    now = clock.utc_now()
    return DecoderHealth(
        process_up=up,
        capturing=capturing,
        last_ping_utc=now - timedelta(seconds=ping_age),
        last_api_reply_utc=None,
        last_audio_write_utc=now,
    )


def healthy() -> tuple[HealthTracker, ManualClock]:
    clock = ManualClock()
    h = HealthTracker(clock)
    h.decoder_link(True)
    h.decoder_facts(facts(clock))
    h.receiver("connected")
    h.audio()
    h.waterfall()
    return h, clock


def test_initial_state_is_offline_not_ok() -> None:
    h = HealthTracker(ManualClock())
    snap = h.snapshot()
    assert snap.overall == "offline"
    assert snap.components.bridge.state == "ok"
    assert snap.components.decoder_process.state == "down"
    assert snap.components.receiver.state == "unknown"
    assert snap.last_decode_utc is None


def test_all_evidence_fresh_is_listening() -> None:
    h, _ = healthy()
    snap = h.snapshot()
    assert snap.overall == "listening"
    assert {c["state"] for c in snap.components.model_dump().values()} == {"ok"}


def test_audio_and_waterfall_go_stale_deterministically() -> None:
    h, clock = healthy()
    clock.advance(2.9)
    h.decoder_facts(facts(clock))
    assert h.snapshot().components.audio.state == "ok"
    clock.advance(0.2)
    h.decoder_facts(facts(clock))
    snap = h.snapshot()
    assert snap.components.audio.state == "down"
    assert "stale" in snap.components.audio.detail
    assert snap.components.waterfall.state == "ok"  # 5 s threshold
    assert snap.overall == "degraded"
    clock.advance(2.0)
    assert h.snapshot().components.waterfall.state == "down"


def test_decoder_crash_while_bridge_stays_up() -> None:
    h, clock = healthy()
    h.decoder_facts(facts(clock, up=False, capturing=False))
    snap = h.snapshot()
    assert snap.components.bridge.state == "ok"
    assert snap.components.decoder_process.state == "down"
    assert snap.components.decoder_api.state == "down"
    assert snap.components.decoder_capture.state == "down"
    assert snap.overall == "offline"


def test_agent_link_loss_is_decoder_down() -> None:
    h, _ = healthy()
    h.decoder_link(False)
    snap = h.snapshot()
    assert snap.components.decoder_process.state == "down"
    assert snap.components.decoder_process.detail == "decoder agent unreachable"


def test_stale_decoder_reports_mean_down() -> None:
    h, clock = healthy()
    clock.advance(11)
    snap = h.snapshot()
    assert snap.components.decoder_process.state == "down"
    assert "no decoder report" in snap.components.decoder_process.detail


def test_api_heartbeat_staleness() -> None:
    h, clock = healthy()
    h.decoder_facts(facts(clock, ping_age=41))
    assert h.snapshot().components.decoder_api.state == "down"
    h.decoder_facts(facts(clock, ping_age=5))
    assert h.snapshot().components.decoder_api.state == "ok"


def test_not_capturing_is_reported() -> None:
    h, clock = healthy()
    h.decoder_facts(facts(clock, capturing=False))
    snap = h.snapshot()
    assert snap.components.decoder_capture.state == "down"
    assert snap.overall == "degraded"


def test_receiver_states() -> None:
    h, _ = healthy()
    h.receiver("backoff", "reconnecting in 10s")
    snap = h.snapshot()
    assert snap.components.receiver.state == "degraded"
    assert snap.components.audio.state == "unknown"  # not "stale": there is no receiver
    assert snap.overall == "offline"
    h.receiver("rejected", "all 4 client slots taken")
    assert h.snapshot().components.receiver.detail == "all 4 client slots taken"


def test_since_only_moves_on_state_change() -> None:
    h, clock = healthy()
    first = h.snapshot().components.audio.since
    clock.advance(1)
    h.audio()
    assert h.snapshot().components.audio.since == first
    clock.advance(4)
    h.decoder_facts(facts(clock))
    down = h.snapshot().components.audio
    assert down.state == "down"
    assert down.since == clock.utc_now()


def test_last_decode_is_only_set_by_decodes() -> None:
    h, clock = healthy()
    assert h.snapshot().last_decode_utc is None
    t = clock.utc_now()
    h.decoded(t)
    h.decoded(t - timedelta(seconds=30))  # older decode never moves it backwards
    assert h.snapshot().last_decode_utc == t


def test_poll_reports_changes_only() -> None:
    h, clock = healthy()
    _, changed = h.poll()
    assert changed
    _, changed = h.poll()
    assert not changed
    clock.advance(4)
    h.decoder_facts(facts(clock))
    _, changed = h.poll()
    assert changed

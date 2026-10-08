from datetime import UTC, datetime, timedelta

from ghostjs8.ghostnet.schedule import (
    GHOSTNET_20M_HZ,
    GHOSTNET_40M_HZ,
    GHOSTNET_80M_HZ,
    PLAN,
    Region,
    active,
    upcoming,
    windows_for,
)


def at(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def test_plan_matches_ghostnet_v15() -> None:
    by_id = {w.id: w for w in PLAN}
    na = by_id["na-net"]
    assert (na.weekday, na.start.hour, na.minutes, na.dial_hz) == (4, 1, 30, 7_107_000)  # Fri 0100Z
    assert by_id["eu-net"].weekday == 3
    assert by_id["eu-net"].start.hour == 18
    assert by_id["aus-net"].start.hour == 7
    assert {w.dial_hz for w in PLAN} == {GHOSTNET_40M_HZ, GHOSTNET_20M_HZ, GHOSTNET_80M_HZ}
    assert GHOSTNET_40M_HZ != 7_078_000  # GhostNet deliberately avoids the standard JS8 frequency


def test_region_membership() -> None:
    assert [w.id for w in windows_for(Region.NA)] == [
        "na-net",
        "na-eu-20m",
        "na-aus-20m",
        "na-aus-80m",
    ]
    assert "aus-sp-40m" in {w.id for w in windows_for(Region.AUS)}
    assert "aus-sp-40m" not in {w.id for w in windows_for(Region.EU)}


def test_upcoming_from_thursday_evening_us_time() -> None:
    # Thu 2026-10-08 23:00Z: the NA net is Fri 01:00Z
    occ = upcoming(Region.NA, at("2026-10-08T23:00:00"))
    assert occ[0].window.id == "na-net"
    assert occ[0].start == at("2026-10-09T01:00:00")
    assert occ[0].key == "na-net@2026-10-09T01:00Z"
    assert [o.window.id for o in occ[1:3]] == ["na-aus-20m", "na-aus-80m"]  # Sat 12:00, 13:30


def test_in_progress_window_is_returned_and_rolls_to_next_week() -> None:
    now = at("2026-10-09T01:20:00")
    assert upcoming(Region.NA, now)[0].start == at("2026-10-09T01:00:00")
    later = at("2026-10-09T01:31:00")
    nxt = next(o for o in upcoming(Region.NA, later, 10) if o.window.id == "na-net")
    assert nxt.start == at("2026-10-16T01:00:00")


def test_active_with_preroll() -> None:
    assert active(Region.NA, at("2026-10-09T00:49:00")) is None
    pre = active(Region.NA, at("2026-10-09T00:51:00"))
    assert pre is not None
    assert pre.window.id == "na-net"
    assert active(Region.NA, at("2026-10-09T01:29:59")) is not None
    assert active(Region.NA, at("2026-10-09T01:30:00")) is None


def test_in_progress_window_wins_over_next_preroll() -> None:
    # AUS: 08:00-09:00 20 m bridge, then 09:00-09:30 40 m bridge
    now = at("2026-10-10T08:55:00")
    occ = active(Region.AUS, now)
    assert occ is not None
    assert occ.window.id == "aus-sp-20m"
    nxt = active(Region.AUS, now + timedelta(minutes=5))
    assert nxt is not None
    assert nxt.window.id == "aus-sp-40m"

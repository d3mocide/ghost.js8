from datetime import timedelta

from ghostjs8.contract.messages import Decode
from ghostjs8.store.sqlite import Store
from ghostjs8.util.clock import ManualClock


def decode(clock: ManualClock, text: str) -> Decode:
    return Decode(
        kind="activity", utc=clock.utc_now(), text=text, snr_db=-10, offset_hz=700, speed="normal"
    )


def test_decodes_roundtrip_oldest_first_and_limited() -> None:
    clock = ManualClock()
    s = Store(":memory:", clock)
    for i in range(5):
        s.add_decode(decode(clock, f"m{i}"))
        clock.advance(15)
    assert [d.text for d in s.recent_decodes(limit=3)] == ["m2", "m3", "m4"]


def test_station_upsert_keeps_last_valid_grid_and_counts() -> None:
    clock = ManualClock()
    s = Store(":memory:", clock)
    s.heard("K0OG", clock.utc_now(), snr_db=-20, grid="EN34", offset_hz=700, dial_hz=14_078_000)
    clock.advance(30)
    st = s.heard("K0OG", clock.utc_now(), snr_db=-12, grid=None, offset_hz=None, dial_hz=None)
    assert (st.grid, st.snr_db, st.offset_hz, st.heard_count) == ("EN34", -12, 700, 2)
    assert st.last_heard_utc == clock.utc_now()
    st = s.heard(
        "K0OG",
        clock.utc_now() - timedelta(hours=1),
        snr_db=None,
        grid=None,
        offset_hz=None,
        dial_hz=None,
        count=False,
    )
    assert st.last_heard_utc == clock.utc_now()  # never moves backwards
    assert st.heard_count == 2


def test_stations_window_and_prune() -> None:
    clock = ManualClock()
    s = Store(":memory:", clock, retention_days=1)
    s.heard("OLD", clock.utc_now(), snr_db=None, grid=None, offset_hz=None, dial_hz=None)
    s.add_decode(decode(clock, "old"))
    clock.advance(2 * 86400)
    s.heard("NEW", clock.utc_now(), snr_db=None, grid=None, offset_hz=None, dial_hz=None)
    assert [x.callsign for x in s.stations()] == ["NEW"]
    assert s.prune() == 2
    assert s.station("OLD") is None
    assert s.recent_decodes() == []


def test_file_backed_wal(tmp_path) -> None:  # type: ignore[no-untyped-def]
    clock = ManualClock()
    path = tmp_path / "db" / "ghost.sqlite3"
    s = Store(path, clock)
    s.add_decode(decode(clock, "persist me"))
    s.close()
    assert [d.text for d in Store(path, clock).recent_decodes()] == ["persist me"]

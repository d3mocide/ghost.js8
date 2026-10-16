from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ghostjs8.api.app import create_app
from ghostjs8.api.hub import Hub
from ghostjs8.contract.messages import (
    Error,
    GhostNet,
    ReceiverRef,
    SetGhostNetSettings,
    server_message_adapter,
)
from ghostjs8.ghostnet import settings as gs
from ghostjs8.ghostnet.pilot import GhostNetPilot, PilotConfig, build_pilot, disabled_status
from ghostjs8.ghostnet.schedule import PLAN, Region, active, upcoming, windows_for
from ghostjs8.ghostnet.settings import (
    AutopilotSettings,
    SettingsError,
    WindowPref,
    apply_update,
    defaults,
)
from ghostjs8.receivers.directory import Directory
from ghostjs8.session.station import Station
from ghostjs8.settings import Settings
from ghostjs8.store.sqlite import Store
from ghostjs8.util.clock import ManualClock
from ghostjs8.util.maidenhead import grid_center
from tests.unit.test_ghostnet_pilot import FakeDecoder, at, fetch

NA_IDS = [w.id for w in windows_for(Region.NA)]


def base() -> AutopilotSettings:
    return defaults(NA_IDS, park=True, record_audio=True)


def update(**kw: Any) -> SetGhostNetSettings:
    return SetGhostNetSettings.model_validate({"v": 1, "type": "ghostnet_settings", **kw})


MID = ReceiverRef(host="mid.example", port=8073, name="Mid RX")


# ------------------------------------------------------------- settings model


def test_defaults_follow_every_window_unless_the_environment_narrows_them() -> None:
    assert base().enabled_ids() == set(NA_IDS)
    narrowed = defaults(NA_IDS, park=False, record_audio=False, default_windows={"na-net"})
    assert narrowed.enabled_ids() == {"na-net"}
    assert (narrowed.park, narrowed.record_audio) == (False, False)


def test_json_round_trip_keeps_everything() -> None:
    s = AutopilotSettings(
        autopilot_enabled=False,
        park=False,
        record_audio=False,
        windows={**base().windows, "na-net": WindowPref(enabled=False, receiver=MID)},
    )
    assert gs.from_json(gs.to_json(s), base()) == s


@pytest.mark.parametrize(
    "stored",
    [None, "", "not json", "[]", '{"windows": 5}', '{"autopilot_enabled": "yes", "park": 3}'],
)
def test_garbage_in_the_store_falls_back_to_the_defaults(stored: str | None) -> None:
    assert gs.from_json(stored, base()) == base()


def test_stored_windows_the_plan_no_longer_has_are_dropped_and_bad_receivers_ignored() -> None:
    text = json.dumps(
        {
            "windows": {
                "gone-window": {"enabled": False},
                "na-net": {"enabled": False, "receiver": {"host": "", "port": 99999}},
            }
        }
    )
    got = gs.from_json(text, base())
    assert "gone-window" not in got.windows
    assert got.windows["na-net"] == WindowPref(enabled=False, receiver=None)


def test_apply_update_changes_only_what_it_names() -> None:
    new = apply_update(
        base(),
        update(
            park=False,
            windows={"na-net": {"enabled": False}, "na-eu-20m": {"receiver": MID.model_dump()}},
        ),
    )
    assert new.park is False
    assert new.autopilot_enabled is True
    assert new.record_audio is True
    assert new.windows["na-net"].enabled is False
    assert new.windows["na-eu-20m"] == WindowPref(enabled=True, receiver=MID)
    assert new.windows["na-aus-20m"] == WindowPref()  # untouched


def test_apply_update_can_clear_a_receiver_and_never_half_applies() -> None:
    pinned = apply_update(base(), update(windows={"na-net": {"receiver": MID.model_dump()}}))
    cleared = apply_update(pinned, update(windows={"na-net": {"clear_receiver": True}}))
    assert cleared.windows["na-net"].receiver is None
    with pytest.raises(SettingsError, match="unknown window"):
        apply_update(base(), update(park=False, windows={"na-net": {"enabled": False}, "nope": {}}))
    with pytest.raises(SettingsError, match="not both"):
        apply_update(
            base(),
            update(windows={"na-net": {"receiver": MID.model_dump(), "clear_receiver": True}}),
        )


def test_store_persists_settings_and_overwrites() -> None:
    store = Store(":memory:", ManualClock())
    assert store.setting("k") is None
    store.save_setting("k", "1")
    store.save_setting("k", "2")
    assert store.setting("k") == "2"


# ------------------------------------------------------------------- schedule


def test_schedule_can_be_restricted_to_enabled_windows() -> None:
    now = at("2026-10-08T20:00:00")  # Thu evening: the next NA window is Fri 01:00
    assert upcoming(Region.NA, now, 1)[0].window.id == "na-net"
    assert upcoming(Region.NA, now, 1, only={"na-eu-20m"})[0].window.id == "na-eu-20m"
    assert upcoming(Region.NA, now, 5, only=set()) == []
    in_net = at("2026-10-09T01:05:00")
    assert active(Region.NA, in_net) is not None
    assert active(Region.NA, in_net, only={"na-eu-20m"}) is None
    assert {w.id for w in PLAN} >= set(NA_IDS)


# ---------------------------------------------------------------------- pilot


def make(
    tmp_path: Path,
    start: str,
    *,
    store: Store | None = None,
    clock: ManualClock | None = None,
    **cfg: Any,
) -> tuple[GhostNetPilot, Station, ManualClock, Store]:
    clock = clock or ManualClock(at(start))
    store = store or Store(":memory:", clock)
    station = Station(Hub(), FakeDecoder, clock=clock, store=store)  # type: ignore[arg-type]
    config = PilotConfig(
        region=Region.NA,
        home_grid="EM73",
        home=grid_center("EM73"),
        recordings=tmp_path,
        record_audio=False,
        **cfg,
    )
    return (
        GhostNetPilot(station, Directory(fetch=fetch, clock=clock), store, config, clock),
        station,
        clock,
        store,
    )


async def test_a_disabled_window_is_not_followed_or_recorded(tmp_path: Path) -> None:
    pilot, _, _, _ = make(tmp_path, "2026-10-09T00:55:00")  # NA net pre-roll
    assert pilot.update_settings(update(windows={"na-net": {"enabled": False}})) is None
    await pilot.tick()
    assert pilot.mode == "parked"
    assert pilot.recorder is None
    nxt = pilot.status().next_window
    assert nxt is not None
    assert nxt.id != "na-net"


async def test_master_switch_off_leaves_the_station_alone(tmp_path: Path) -> None:
    pilot, station, _, _ = make(tmp_path, "2026-10-09T00:55:00")
    assert pilot.update_settings(update(autopilot_enabled=False)) is None
    await pilot.tick()
    assert pilot.mode == "off"
    assert station.target is None
    assert pilot.recorder is None
    assert pilot.status().autopilot_enabled is False
    assert pilot.update_settings(update(autopilot_enabled=True)) is None
    await pilot.tick()
    assert pilot.mode == "window"
    assert pilot.recorder is not None


async def test_switching_off_mid_window_stops_and_finishes_the_recording(tmp_path: Path) -> None:
    pilot, station, clock, store = make(tmp_path, "2026-10-09T01:05:00")
    await pilot.tick()
    assert pilot.recorder is not None
    nid = pilot.recorder.summary.id
    assert pilot.update_settings(update(windows={"na-net": {"enabled": False}})) is None
    clock.advance(5)
    await pilot.tick()
    assert pilot.recorder is None
    assert pilot.recorder not in station.observers
    finished = store.net(nid)
    assert finished is not None
    assert finished.ended is not None


async def test_park_and_record_audio_switches_apply_live(tmp_path: Path) -> None:
    pilot, station, _, _ = make(tmp_path, "2026-10-08T20:00:00")
    assert pilot.update_settings(update(park=False)) is None
    await pilot.tick()
    assert pilot.mode == "off"
    assert station.target is None
    assert pilot.update_settings(update(park=True, record_audio=True)) is None
    await pilot.tick()
    assert pilot.mode == "parked"
    assert pilot.status().record_audio is True


async def test_settings_survive_a_restart_and_the_app_wins_over_the_environment(
    tmp_path: Path,
) -> None:
    pilot, _, clock, store = make(
        tmp_path, "2026-10-08T20:00:00", default_windows=frozenset({"na-net"})
    )
    assert pilot.settings.enabled_ids() == {"na-net"}  # seeded by GHOSTJS8_GHOSTNET_WINDOWS
    assert (
        pilot.update_settings(
            update(windows={"na-aus-20m": {"enabled": True, "receiver": MID.model_dump()}})
        )
        is None
    )
    reborn, _, _, _ = make(
        tmp_path,
        "2026-10-08T20:00:00",
        store=store,
        clock=clock,
        default_windows=frozenset({"na-net"}),
    )
    assert reborn.settings.enabled_ids() == {"na-net", "na-aus-20m"}  # what the app saved wins
    assert reborn.settings.windows["na-aus-20m"].receiver == MID


async def test_invalid_updates_report_why_and_change_nothing(tmp_path: Path) -> None:
    pilot, _, _, store = make(tmp_path, "2026-10-08T20:00:00")
    before = pilot.settings
    problem = pilot.update_settings(update(park=False, windows={"made-up": {"enabled": False}}))
    assert problem is not None
    assert "made-up" in problem
    assert pilot.settings == before
    assert store.setting(gs.KEY) is None  # nothing persisted


async def test_status_lists_every_window_with_its_settings(tmp_path: Path) -> None:
    pilot, _, _, _ = make(tmp_path, "2026-10-08T20:00:00")
    pilot.update_settings(
        update(windows={"na-net": {"enabled": False, "receiver": MID.model_dump()}})
    )
    status = pilot.status()
    assert [w.id for w in status.windows] == NA_IDS
    net = next(w for w in status.windows if w.id == "na-net")
    assert (net.enabled, net.receiver) == (False, MID)
    assert (net.weekday, net.start, net.minutes, net.band) == (4, "01:00", 30, "40m")
    assert next(w for w in status.windows if w.id == "na-eu-20m").enabled is True


async def test_preferred_receiver_beats_the_nearest_for_its_window(tmp_path: Path) -> None:
    pilot, station, _, _ = make(tmp_path, "2026-10-09T00:55:00")
    pilot.update_settings(update(windows={"na-net": {"receiver": MID.model_dump()}}))
    await pilot.tick()
    assert station.target is not None
    assert station.target.host == "mid.example"  # not "near.example"
    assert pilot.reason == "your preferred receiver for this net"
    assert pilot.detail == ""


async def test_preference_moves_a_working_park_receiver_when_the_window_starts(
    tmp_path: Path,
) -> None:
    pilot, station, clock, _ = make(tmp_path, "2026-10-09T00:30:00")
    pilot.update_settings(update(windows={"na-net": {"receiver": MID.model_dump()}}))
    await pilot.tick()
    assert station.target is not None
    assert station.target.host == "near.example"  # parked on the nearest
    station.state = "connected"
    clock.advance(25 * 60)  # 00:55, pre-roll
    await pilot.tick()
    assert station.target.host == "mid.example"  # a working feed still yields to the preference


async def test_preference_is_ignored_outside_its_window(tmp_path: Path) -> None:
    pilot, station, _, _ = make(tmp_path, "2026-10-08T20:00:00")  # parked, no window
    pilot.update_settings(update(windows={"na-net": {"receiver": MID.model_dump()}}))
    await pilot.tick()
    assert station.target is not None
    assert station.target.host == "near.example"


async def test_failed_preference_falls_back_and_stays_off_until_the_window_ends(
    tmp_path: Path,
) -> None:
    pilot, station, clock, _ = make(tmp_path, "2026-10-09T00:55:00")
    pilot.update_settings(update(windows={"na-net": {"receiver": MID.model_dump()}}))
    await pilot.tick()
    assert station.target is not None
    assert station.target.host == "mid.example"
    station.state = "rejected"
    await pilot.tick()
    assert station.target.host == "near.example"  # the picker took over
    assert pilot.detail == "your preferred receiver is unavailable; using the best other"
    station.state = "connected"
    clock.advance(10 * 60)
    await pilot.tick()
    assert station.target.host == "near.example"  # no flapping back mid-window


async def test_a_preferred_receiver_missing_from_the_directory_falls_back(tmp_path: Path) -> None:
    pilot, station, _, _ = make(tmp_path, "2026-10-09T00:55:00")
    ghost = ReceiverRef(host="not-listed.example", port=8073)
    pilot.update_settings(update(windows={"na-net": {"receiver": ghost.model_dump()}}))
    await pilot.tick()
    assert station.target is not None
    assert station.target.host == "near.example"
    assert "preferred receiver is unavailable" in pilot.detail


async def test_viewer_taking_control_still_pauses_but_settings_edits_do_not(tmp_path: Path) -> None:
    pilot, station, _, _ = make(tmp_path, "2026-10-09T01:05:00")
    await pilot.tick()
    pilot.update_settings(update(park=False))
    assert pilot.mode != "paused"
    assert pilot.paused_until is None
    station.operator_changed()
    assert pilot.mode == "paused"


# ----------------------------------------------------- environment and the wire


def test_environment_window_filter_is_validated(tmp_path: Path) -> None:
    store = Store(":memory:", ManualClock())
    station = Station(Hub(), FakeDecoder, store=store)  # type: ignore[arg-type]
    common = {
        "ghostnet": True,
        "ghostnet_region": "na",
        "home_grid": "EM73",
        "recordings_dir": str(tmp_path),
    }
    directory = Directory(fetch=fetch)
    bad, why = build_pilot(
        Settings(**common, ghostnet_windows="na-net,nope"),  # type: ignore[arg-type]
        station,
        directory,
        ManualClock(),
    )
    assert bad is None
    assert "nope" in why
    good, why = build_pilot(
        Settings(**common, ghostnet_windows=" na-net , na-eu-20m "),  # type: ignore[arg-type]
        station,
        directory,
        ManualClock(),
    )
    assert good is not None, why
    assert good.settings.enabled_ids() == {"na-net", "na-eu-20m"}


def app_for(pilot: GhostNetPilot | None, station: Station, tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            station,
            Settings(db_path=":memory:", recordings_dir=str(tmp_path)),
            directory=Directory(fetch=fetch),
        )
    )


def drain(ws: Any, until: type, limit: int = 20) -> list[object]:
    seen: list[object] = []
    for _ in range(limit):
        msg = server_message_adapter.validate_json(ws.receive_text())
        seen.append(msg)
        if isinstance(msg, until):
            return seen
    raise AssertionError(f"never saw {until.__name__}: {seen}")


def test_ws_settings_message_updates_the_autopilot_and_broadcasts(tmp_path: Path) -> None:
    pilot, station, _, store = make(tmp_path, "2026-10-08T20:00:00")
    with app_for(pilot, station, tmp_path) as http, http.websocket_connect("/ws") as ws:
        drain(ws, GhostNet)  # the status every new viewer gets
        ws.send_text(
            json.dumps(
                {
                    "v": 1,
                    "type": "ghostnet_settings",
                    "park": False,
                    "windows": {"na-net": {"enabled": False, "receiver": MID.model_dump()}},
                }
            )
        )
        status = drain(ws, GhostNet)[-1]
        assert isinstance(status, GhostNet)
        assert status.park is False
        net = next(w for w in status.windows if w.id == "na-net")
        assert (net.enabled, net.receiver) == (False, MID)
    assert pilot.mode != "paused"  # editing settings is not "taking manual control"
    assert pilot.paused_until is None
    assert store.setting(gs.KEY) is not None


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"windows": {"made-up": {"enabled": False}}}, "invalid_settings"),
        (
            {"windows": {"na-net": {"receiver": {"host": "127.0.0.1", "port": 8073}}}},
            "invalid_receiver",
        ),
        (
            {"windows": {"na-net": {"receiver": MID.model_dump(), "clear_receiver": True}}},
            "invalid_settings",
        ),
        ({"windows": {"na-net": {"enabled": "maybe"}}}, "bad_message"),
        ({"autopilot_enabled": 5}, "bad_message"),
    ],
)
def test_ws_rejects_bad_settings_without_changing_anything(
    tmp_path: Path, payload: dict[str, Any], code: str
) -> None:
    pilot, station, _, store = make(tmp_path, "2026-10-08T20:00:00")
    before = pilot.settings
    with app_for(pilot, station, tmp_path) as http, http.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"v": 1, "type": "ghostnet_settings", **payload}))
        err = drain(ws, Error)[-1]
        assert isinstance(err, Error)
        assert err.code == code
    assert pilot.settings == before
    assert store.setting(gs.KEY) is None


def test_ws_settings_without_an_autopilot_says_so(tmp_path: Path) -> None:
    station = Station(Hub(), FakeDecoder, store=Store(":memory:", ManualClock()))  # type: ignore[arg-type]
    assert station.ghostnet_settings is None
    with app_for(None, station, tmp_path) as http, http.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"v": 1, "type": "ghostnet_settings", "park": False}))
        err = drain(ws, Error)[-1]
        assert isinstance(err, Error)
        assert err.code == "unavailable"


def test_disabled_status_carries_the_new_fields() -> None:
    s = disabled_status("off")
    assert (s.autopilot_enabled, s.park, s.record_audio, s.windows) == (False, False, False, [])

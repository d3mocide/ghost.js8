from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ghostjs8.api.hub import Hub
from ghostjs8.contract.messages import GhostNet, server_message_adapter
from ghostjs8.decoders.base import DecodeEvent, DecoderSink
from ghostjs8.ghostnet.picker import NO_AUDIO_COOLDOWN
from ghostjs8.ghostnet.pilot import GhostNetPilot, PilotConfig, net_id
from ghostjs8.ghostnet.schedule import Region
from ghostjs8.receivers.directory import Directory
from ghostjs8.session.station import Station
from ghostjs8.store.sqlite import Store
from ghostjs8.util.clock import ManualClock
from ghostjs8.util.maidenhead import grid_center


class FakeDecoder:
    connected = True

    def __init__(self, sink: DecoderSink) -> None:
        self.sink = sink

    def submit_audio(self, pcm_s16le: bytes) -> None:
        pass

    async def run(self) -> None:
        await asyncio.Event().wait()

    async def close(self) -> None:
        pass


DIRECTORY = b"""var kiwisdr_com = [
 {"id":"near","status":"active","offline":"no","name":"Near RX","bands":"0-30000000","users":"0","users_max":"4",
  "gps":"(33.9, -84.3)","snr":"30","url":"http://near.example:8073"},
 {"id":"mid","status":"active","offline":"no","name":"Mid RX","bands":"0-30000000","users":"1","users_max":"4",
  "gps":"(36.1, -86.7)","snr":"30","url":"http://mid.example:8073"},
 {"id":"far","status":"active","offline":"no","name":"Far RX","bands":"0-30000000","users":"0","users_max":"4",
  "gps":"(47.6, -122.3)","snr":"30","url":"https://far.example:443"},
];"""


def at(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


async def fetch(_: str) -> bytes:
    return DIRECTORY


def make(
    tmp_path: Path, start: str, *, park: bool = True
) -> tuple[GhostNetPilot, Station, ManualClock, Store]:
    clock = ManualClock(at(start))
    store = Store(":memory:", clock)
    station = Station(Hub(), FakeDecoder, clock=clock, store=store)
    cfg = PilotConfig(
        region=Region.NA,
        home_grid="EM73",
        home=grid_center("EM73"),
        recordings=tmp_path,
        park=park,
        record_audio=False,
    )
    pilot = GhostNetPilot(station, Directory(fetch=fetch, clock=clock), store, cfg, clock)
    return pilot, station, clock, store


def event(clock: ManualClock, text: str, frm: str) -> DecodeEvent:
    return DecodeEvent(
        kind="activity",
        utc=clock.utc_now(),
        text=text,
        snr_db=-10,
        offset_hz=800,
        speed="normal",
        from_call=frm,
    )


async def test_parks_on_7107_with_nearest_receiver_between_windows(tmp_path: Path) -> None:
    pilot, station, _, _ = make(tmp_path, "2026-10-08T20:00:00")  # Thu evening UTC, no window
    await pilot.tick()
    assert pilot.mode == "parked"
    assert station.tuning.dial_hz == 7_107_000
    assert station.target is not None
    assert station.target.host == "near.example"
    assert pilot.recorder is None
    assert pilot.reason.startswith("nearest free receiver")


async def test_no_park_means_off(tmp_path: Path) -> None:
    pilot, station, _, _ = make(tmp_path, "2026-10-08T20:00:00", park=False)
    await pilot.tick()
    assert pilot.mode == "off"
    assert station.target is None


async def test_window_preroll_starts_recording_and_finishes_with_traffic(tmp_path: Path) -> None:
    pilot, station, clock, store = make(tmp_path, "2026-10-09T00:51:00")  # NA net pre-roll
    await pilot.tick()
    assert pilot.mode == "window"
    assert pilot.recorder is not None
    nid = pilot.recorder.summary.id
    assert nid == "na-net-20261009T0100Z"
    assert pilot.recorder in station.observers
    clock.advance(600)
    station.on_decode(event(clock, "K0OG: @GHOSTNET QSL", "K0OG"))
    station.on_decode(event(clock, "W1GHZ: @GSTFLASH TEST", "W1GHZ"))
    clock.advance(30 * 60)  # 01:31, window over
    await pilot.tick()
    assert pilot.recorder is None
    assert pilot.mode == "parked"
    net = store.net(nid)
    assert net is not None
    assert net.ended is not None
    assert (net.decode_count, net.station_count, net.flash_count) == (2, 2, 1)
    assert net.receiver is not None
    assert "near.example" in net.receiver


async def test_saturday_bridge_retunes_to_20m(tmp_path: Path) -> None:
    pilot, station, _, _ = make(tmp_path, "2026-10-10T12:05:00")  # NA-AUS 20 m bridge
    await pilot.tick()
    assert pilot.window is not None
    assert pilot.window.window.id == "na-aus-20m"
    assert station.tuning.dial_hz == 14_107_000


async def test_rejected_receiver_is_benched_and_next_nearest_tried(tmp_path: Path) -> None:
    pilot, station, _, _ = make(tmp_path, "2026-10-08T20:00:00")
    await pilot.tick()
    assert station.target is not None
    assert station.target.host == "near.example"
    station.state = "rejected"
    await pilot.tick()
    assert station.target.host == "mid.example"


async def test_slow_connect_falls_back_after_grace(tmp_path: Path) -> None:
    pilot, station, clock, _ = make(tmp_path, "2026-10-08T20:00:00")
    await pilot.tick()
    station.state = "connecting"
    clock.advance(30)
    await pilot.tick()
    assert station.target is not None
    assert station.target.host == "near.example"  # still within grace
    clock.advance(31)
    await pilot.tick()
    assert station.target.host == "mid.example"


async def test_operator_override_pauses_until_window_end(tmp_path: Path) -> None:
    pilot, station, clock, store = make(tmp_path, "2026-10-09T01:05:00")
    await pilot.tick()
    nid = net_id(pilot.window)  # type: ignore[arg-type]
    station.operator_changed()
    assert pilot.mode == "paused"
    assert pilot.paused_until == at("2026-10-09T01:30:00")
    from ghostjs8.receivers.base import Tuning  # noqa: PLC0415

    await station.tune(Tuning(dial_hz=14_078_000))
    clock.advance(60)
    await pilot.tick()
    assert station.tuning.dial_hz == 14_078_000  # not fought over
    assert pilot.recorder is not None  # still recording
    clock.advance(30 * 60)
    await pilot.tick()
    assert pilot.mode == "parked"
    assert station.tuning.dial_hz == 7_107_000
    net = store.net(nid)
    assert net is not None
    assert net.operator_override


async def test_status_is_broadcast_and_sent_to_new_viewers(tmp_path: Path) -> None:
    pilot, station, _, _ = make(tmp_path, "2026-10-08T20:00:00")
    watcher = station.hub.add()
    await pilot.tick()
    msgs = []
    while not watcher.queue.empty():
        raw = watcher.queue.get_nowait()
        assert isinstance(raw, str)
        msgs.append(server_message_adapter.validate_python(json.loads(raw)))
    status = [m for m in msgs if isinstance(m, GhostNet)]
    assert status
    assert status[-1].mode == "parked"
    assert status[-1].next_window is not None
    assert status[-1].next_window.id == "na-net"
    joiner = station.hub.add()
    station.client_joined(joiner)
    kinds = []
    while not joiner.queue.empty():
        raw = joiner.queue.get_nowait()
        assert isinstance(raw, str)
        kinds.append(json.loads(raw)["type"])
    assert "ghostnet" in kinds


async def test_already_recorded_window_is_not_overwritten(tmp_path: Path) -> None:
    pilot, _, clock, store = make(tmp_path, "2026-10-09T01:05:00")
    await pilot.tick()
    occ = pilot.window
    assert occ is not None
    clock.advance(30 * 60)
    await pilot.tick()
    finished = store.net(net_id(occ))
    assert finished is not None
    assert finished.ended is not None
    # e.g. a restarted bridge re-entering the same, already finished window
    pilot._start_recording(occ, clock.utc_now())
    assert pilot.recorder is None
    assert store.net(net_id(occ)) == finished


@pytest.mark.parametrize("start", ["2026-10-09T00:49:00"])
async def test_before_preroll_is_parked(tmp_path: Path, start: str) -> None:
    pilot, _, _, _ = make(tmp_path, start)
    await pilot.tick()
    assert pilot.mode == "parked"
    assert pilot.recorder is None
    assert pilot.status().next_window is not None
    assert pilot.status().next_window.start == at("2026-10-09T01:00:00")  # type: ignore[union-attr]
    assert timedelta(minutes=10) == pilot.config.preroll


async def test_working_receiver_chosen_by_a_viewer_is_kept_after_the_pause(tmp_path: Path) -> None:
    from ghostjs8.session.station import ReceiverTarget  # noqa: PLC0415

    pilot, station, clock, _ = make(tmp_path, "2026-10-08T20:00:00")
    await pilot.tick()
    assert station.target is not None
    assert station.target.host == "near.example"  # the autopilot's own pick

    station.select_receiver(ReceiverTarget("mid.example", 8073))  # a viewer chooses another
    station.state = "connected"
    station.operator_changed()
    assert pilot.mode == "paused"

    clock.advance(5 * 3600)  # past the pause: the next net's pre-roll is under way
    await pilot.tick()
    assert pilot.mode == "window"
    assert station.target is not None
    assert station.target.host == "mid.example"  # not swapped for the "nearest" one
    assert pilot.listing is not None
    assert pilot.listing.id == "mid"


async def test_silent_receiver_is_benched_for_hours_not_minutes(tmp_path: Path) -> None:
    pilot, station, clock, _ = make(tmp_path, "2026-10-08T20:00:00")
    await pilot.tick()
    assert station.target is not None
    assert station.target.host == "near.example"
    station.state = "backoff"
    station.detail = "no audio within 15s of connecting"
    clock.advance(61)
    await pilot.tick()
    assert station.target.host == "mid.example"

    clock.advance(2 * 3600)  # long past the default 30-minute bench
    station.state = "rejected"
    station.detail = ""
    await pilot.tick()
    assert station.target.host == "far.example"  # near.example is still benched
    assert timedelta(hours=2) < NO_AUDIO_COOLDOWN


async def test_boot_target_gets_the_connect_grace_before_the_autopilot_replaces_it(
    tmp_path: Path,
) -> None:
    from ghostjs8.session.station import ReceiverTarget  # noqa: PLC0415

    pilot, station, clock, _ = make(tmp_path, "2026-10-08T20:00:00")
    station.select_receiver(ReceiverTarget("mid.example", 8073, trusted=True))  # boot target
    station.state = "connecting"
    await pilot.tick()
    assert station.target is not None
    assert station.target.host == "mid.example"  # not swapped on the first tick

    station.state = "connected"  # it came up
    clock.advance(600)
    await pilot.tick()
    assert station.target.host == "mid.example"
    assert pilot.listing is not None
    assert pilot.listing.id == "mid"  # adopted from the directory


async def test_boot_target_that_never_connects_is_replaced_after_the_grace(
    tmp_path: Path,
) -> None:
    from ghostjs8.session.station import ReceiverTarget  # noqa: PLC0415

    pilot, station, clock, _ = make(tmp_path, "2026-10-08T20:00:00")
    station.select_receiver(ReceiverTarget("dead.example", 8073, trusted=True))
    station.state = "connecting"
    await pilot.tick()
    clock.advance(30)
    await pilot.tick()
    assert station.target is not None
    assert station.target.host == "dead.example"
    clock.advance(40)
    await pilot.tick()
    assert station.target.host == "near.example"

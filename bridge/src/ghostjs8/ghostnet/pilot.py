"""GhostNet autopilot: be on the net, on a nearby receiver, and record it.

Every tick (5 s):

- In a window (pre-roll included): make sure a net recording is running, the
  station is tuned to the window's frequency, and it is on a nearby public
  KiwiSDR. A receiver that rejects, fails, or does not connect within the grace
  period is benched and the next-nearest is tried.
- Between windows: park on GhostNet's 40 m frequency and keep decoding
  (persistent watch), unless parking is disabled.
- When a viewer takes manual control, the autopilot yields until the current
  window ends (recording continues and is flagged), or, while parked, until
  the next window.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from ghostjs8.contract.messages import GhostNet, GhostNetWindow, NetSummary, ReceiverListing
from ghostjs8.ghostnet.picker import NO_AUDIO_COOLDOWN, Candidate, ReceiverPicker
from ghostjs8.ghostnet.recorder import NetRecorder, prune_recordings
from ghostjs8.ghostnet.schedule import GHOSTNET_40M_HZ, Occurrence, Region, active, upcoming
from ghostjs8.receivers.base import Tuning
from ghostjs8.receivers.directory import Directory
from ghostjs8.session.station import ReceiverTarget, Station
from ghostjs8.settings import Settings
from ghostjs8.store.sqlite import Store
from ghostjs8.util.clock import Clock
from ghostjs8.util.maidenhead import grid_center, normalize_grid

log = logging.getLogger("ghostjs8.ghostnet.pilot")

Mode = Literal["off", "window", "parked", "paused"]
TICK_S = 5.0
#: Audio must flow this long before a receiver counts as proven.
PROVEN_AFTER = timedelta(seconds=60)
PRUNE_EVERY = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class PilotConfig:
    region: Region
    home_grid: str
    home: tuple[float, float]
    recordings: Path
    preroll: timedelta = timedelta(minutes=10)
    record_audio: bool = True
    park: bool = True
    park_dial_hz: int = GHOSTNET_40M_HZ
    connect_grace: timedelta = timedelta(seconds=60)
    net_retention: timedelta = timedelta(days=90)


def net_id(occ: Occurrence) -> str:
    return f"{occ.window.id}-{occ.start.strftime('%Y%m%dT%H%MZ')}"


def _window_model(occ: Occurrence | None) -> GhostNetWindow | None:
    if occ is None:
        return None
    w = occ.window
    kind: Literal["net", "bridge"] = "net" if w.kind == "net" else "bridge"
    return GhostNetWindow(
        id=w.id,
        label=w.label,
        kind=kind,
        band=w.band,
        dial_hz=w.dial_hz,
        start=occ.start,
        end=occ.end,
    )


class GhostNetPilot:
    def __init__(
        self,
        station: Station,
        directory: Directory,
        store: Store,
        config: PilotConfig,
        clock: Clock,
        *,
        picker: ReceiverPicker | None = None,
    ) -> None:
        self.station = station
        self.directory = directory
        self.store = store
        self.config = config
        self.clock = clock
        self.picker = picker or ReceiverPicker(config.home)
        self.recorder: NetRecorder | None = None
        self.mode: Mode = "parked" if config.park else "off"
        self.window: Occurrence | None = None
        self.paused_until: datetime | None = None
        self.listing: ReceiverListing | None = None
        self.reason = ""
        self.detail = ""
        self._selected_at: datetime | None = None
        self._connected_since: datetime | None = None
        self._foreign_since: datetime | None = None
        self._last_status: str | None = None
        self._last_prune: datetime | None = None
        station.operator_action.append(self.operator_took_control)
        station.join_messages.append(self.status)

    # ------------------------------------------------------------------ loop

    async def run(self) -> None:
        try:
            while True:
                try:
                    await self.tick()
                except Exception:
                    log.exception("ghostnet tick failed")
                await asyncio.sleep(TICK_S)
        finally:
            self._stop_recording()

    async def tick(self) -> None:
        now = self.clock.utc_now()
        occ = active(self.config.region, now, self.config.preroll)

        if occ is not None and (self.window is None or net_id(occ) != net_id(self.window)):
            self._stop_recording()
            self.window = occ
            self.paused_until = None  # a new window always takes the station
            self._start_recording(occ, now)
        elif occ is None and self.window is not None:
            self._stop_recording()
            self.window = None

        if self.paused_until is not None and now >= self.paused_until:
            self.paused_until = None

        if self.paused_until is not None:
            self.mode = "paused"
        elif occ is not None:
            self.mode = "window"
            await self._ensure_on(occ.window.dial_hz, now)
        elif self.config.park:
            self.mode = "parked"
            await self._ensure_on(self.config.park_dial_hz, now)
        else:
            self.mode = "off"

        if self._last_prune is None or now - self._last_prune >= PRUNE_EVERY:
            self._last_prune = now
            removed = prune_recordings(
                self.store, self.config.recordings, self.config.net_retention
            )
            if removed:
                log.info("pruned %d expired net recordings", removed)

        self._publish()

    def operator_took_control(self) -> None:
        now = self.clock.utc_now()
        if self.window is not None:
            self.paused_until = self.window.end
            if self.recorder is not None:
                self.recorder.mark_override()
        else:
            nxt = upcoming(self.config.region, now, 1)
            self.paused_until = (nxt[0].start - self.config.preroll) if nxt else None
        self.mode = "paused"
        self.detail = "a viewer took manual control"
        self._publish()

    # ------------------------------------------------------------- receiver

    async def _ensure_on(self, dial_hz: int, now: datetime) -> None:
        st = self.station
        if st.tuning.dial_hz != dial_hz or st.tuning.mode != "usb":
            await st.tune(Tuning(dial_hz=dial_hz, mode="usb", low_cut_hz=100, high_cut_hz=3000))
        await self._adopt_working_receiver(dial_hz, now)
        self._note_health(now)
        if self._needs_new_receiver(dial_hz, now):
            if self.listing is not None:
                if "no audio" in self.station.detail:
                    # Connected but silent: broken, not busy. Leave it alone for hours.
                    self.picker.bench(self.listing.id, now, NO_AUDIO_COOLDOWN)
                else:
                    self.picker.bench(self.listing.id, now)
                if self.station.state in ("connecting", "backoff"):
                    # Never got a session: the host is unreachable, not merely busy.
                    self.picker.bench_host(self.listing.host, now)
            await self._pick(dial_hz, now)

    async def _adopt_working_receiver(self, dial_hz: int, now: datetime) -> None:
        """Take over a receiver someone else chose, once it is demonstrably working.

        A viewer's pick (or the operator's boot target) that is delivering audio is
        never worth replacing with the "nearest" one: swapping a live feed for an
        untried listing is how a good session ended up on a dead receiver.
        """
        st = self.station
        t = st.target
        if t is None or st.state != "connected":
            return
        ours = self.listing
        if ours is not None and (ours.host, ours.port) == (t.host, t.port):
            return
        try:
            directory = await self.directory.get()
        except Exception:
            return
        found = next((r for r in directory.receivers if (r.host, r.port) == (t.host, t.port)), None)
        if found is not None and found.min_hz <= dial_hz <= found.max_hz:
            self.listing = found
            self.reason = "keeping the receiver you chose"
            self.detail = ""
            self._selected_at = now
            if self.recorder is not None:
                self.recorder.set_receiver(f"{found.name} ({found.host}:{found.port})", self.reason)

    def _note_health(self, now: datetime) -> None:
        """Remember receivers that have streamed audio steadily, so they are preferred."""
        st = self.station
        if st.state != "connected" or self.listing is None:
            self._connected_since = None
            return
        if self._connected_since is None:
            self._connected_since = now
        elif now - self._connected_since >= PROVEN_AFTER:
            self.picker.mark_proven(self.listing.id, now)

    def _needs_new_receiver(self, dial_hz: int, now: datetime) -> bool:
        st = self.station
        ours = self.listing
        if st.state == "connected" and st.target is not None:
            if ours is None or (ours.host, ours.port) != (st.target.host, st.target.port):
                return False  # a feed we did not choose that works (unknown coverage): keep it
            if ours.min_hz <= dial_hz <= ours.max_hz:
                return False  # a working receiver is never worth replacing
        if st.target is None:
            return True
        if ours is None or st.target.host != ours.host or st.target.port != ours.port:
            # Someone else's choice (the operator's boot target, or a viewer's). Give it the
            # same time to connect as one of ours before deciding it is not working.
            if self._foreign_since is None:
                self._foreign_since = now
            return now - self._foreign_since > self.config.connect_grace
        self._foreign_since = None
        if not (ours.min_hz <= dial_hz <= ours.max_hz):
            return True
        if st.state in ("rejected", "failed"):
            return True
        if st.state in ("connecting", "backoff") and self._selected_at is not None:
            return now - self._selected_at > self.config.connect_grace
        return False

    async def _pick(self, dial_hz: int, now: datetime) -> None:
        listing = await self.directory.get()
        candidates: list[Candidate] = self.picker.rank(listing.receivers, dial_hz, now)
        if not candidates:
            self.listing = None
            self.reason = ""
            self.detail = "no free public receiver covers this frequency right now; retrying"
            return
        best = candidates[0]
        r = best.listing
        self.listing = r
        self.reason = best.reason
        self.detail = ""
        self._selected_at = now
        log.info("ghostnet: selecting %s:%d (%s)", r.host, r.port, best.reason)
        self.station.select_receiver(ReceiverTarget(r.host, r.port, name=r.name, tls=r.tls))
        if self.recorder is not None:
            self.recorder.set_receiver(f"{r.name} ({r.host}:{r.port})", best.reason)

    # ------------------------------------------------------------ recording

    def _start_recording(self, occ: Occurrence, now: datetime) -> None:
        w = occ.window
        kind: Literal["net", "bridge"] = "net" if w.kind == "net" else "bridge"
        summary = NetSummary(
            id=net_id(occ),
            window_id=w.id,
            label=w.label,
            kind=kind,
            band=w.band,
            dial_hz=w.dial_hz,
            scheduled_start=occ.start,
            scheduled_end=occ.end,
            started=now,
            ended=None,
            receiver=None,
            receiver_reason="",
            decode_count=0,
            station_count=0,
            has_audio=False,
            has_waterfall=False,
            flash_count=0,
            operator_override=False,
        )
        existing = self.store.net(summary.id)
        if existing is not None and existing.ended is not None:
            return  # already recorded (e.g. bridge restarted after the window)
        self.recorder = NetRecorder(
            self.store,
            self.clock,
            self.config.recordings,
            summary,
            record_audio=self.config.record_audio,
        )
        self.station.observers.append(self.recorder)
        if self.listing is not None:
            self.recorder.set_receiver(
                f"{self.listing.name} ({self.listing.host}:{self.listing.port})", self.reason
            )

    def _stop_recording(self) -> None:
        rec = self.recorder
        if rec is None:
            return
        self.recorder = None
        if rec in self.station.observers:
            self.station.observers.remove(rec)
        rec.finish()

    # --------------------------------------------------------------- status

    def status(self) -> GhostNet:
        now = self.clock.utc_now()
        nxt = [
            o
            for o in upcoming(self.config.region, now, 3)
            if self.window is None or net_id(o) != net_id(self.window)
        ]
        return GhostNet(
            enabled=True,
            region=self.config.region.value,
            home_grid=self.config.home_grid,
            mode=self.mode,
            window=_window_model(self.window),
            next_window=_window_model(nxt[0] if nxt else None),
            recording_net_id=self.recorder.summary.id if self.recorder else None,
            receiver_reason=self.reason,
            paused_until=self.paused_until,
            detail=self.detail,
        )

    def _publish(self) -> None:
        msg = self.status()
        key = msg.model_dump_json(exclude={"v"})
        if key != self._last_status:
            self._last_status = key
            self.station.hub.broadcast(msg)


def disabled_status(detail: str) -> GhostNet:
    return GhostNet(
        enabled=False,
        region=None,
        home_grid=None,
        mode="off",
        window=None,
        next_window=None,
        recording_net_id=None,
        receiver_reason="",
        paused_until=None,
        detail=detail,
    )


def build_pilot(
    settings: Settings, station: Station, directory: Directory, clock: Clock
) -> tuple[GhostNetPilot | None, str]:
    """Construct the autopilot from settings, or explain why it is off."""
    if not settings.ghostnet:
        return None, "GhostNet autopilot is off (GHOSTJS8_GHOSTNET=on to enable)"
    try:
        region = Region(settings.ghostnet_region)
    except ValueError:
        return (
            None,
            f"GHOSTJS8_GHOSTNET_REGION must be na, eu or aus (got {settings.ghostnet_region!r})",
        )
    grid = normalize_grid(settings.home_grid)
    if grid is None:
        return (
            None,
            f"GHOSTJS8_HOME_GRID must be a 4/6/8-character Maidenhead grid (got {settings.home_grid!r})",
        )
    if station.store is None:
        return None, "GhostNet recording needs persistence: set GHOSTJS8_DB_PATH"
    config = PilotConfig(
        region=region,
        home_grid=grid,
        home=grid_center(grid),
        recordings=Path(settings.recordings_dir),
        preroll=timedelta(minutes=max(0, settings.ghostnet_preroll_minutes)),
        record_audio=settings.ghostnet_record_audio,
        park=settings.ghostnet_park,
        net_retention=timedelta(days=max(1, settings.net_retention_days)),
    )
    return GhostNetPilot(station, directory, station.store, config, clock), ""

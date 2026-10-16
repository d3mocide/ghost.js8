"""Operator settings for the GhostNet autopilot, editable from the app.

The environment (``GHOSTJS8_GHOSTNET_*``) says whether the feature exists and seeds the
defaults. What the operator then changes in the app is persisted in the store and wins,
so a restart keeps it. Nothing here touches the station: the pilot reads these.

- ``autopilot_enabled``: master switch. Off, the autopilot leaves the station alone.
- ``park`` / ``record_audio``: the matching environment options, now live.
- per window: ``enabled`` (follow and record it) and an optional preferred receiver.
  A preference, never a lock: if it fails the picker takes over for that window.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field, replace

from pydantic import ValidationError

from ghostjs8.contract.messages import ReceiverRef, SetGhostNetSettings
from ghostjs8.store.sqlite import Store

log = logging.getLogger("ghostjs8.ghostnet.settings")

KEY = "ghostnet.settings.v1"


class SettingsError(ValueError):
    """The requested change is not valid (unknown window, ...). Nothing was applied."""


@dataclass(frozen=True, slots=True)
class WindowPref:
    enabled: bool = True
    receiver: ReceiverRef | None = None


@dataclass(frozen=True, slots=True)
class AutopilotSettings:
    autopilot_enabled: bool = True
    park: bool = True
    record_audio: bool = True
    windows: Mapping[str, WindowPref] = field(default_factory=dict)

    def enabled_ids(self) -> frozenset[str]:
        return frozenset(i for i, w in self.windows.items() if w.enabled)

    def pref(self, window_id: str) -> WindowPref:
        return self.windows.get(window_id, WindowPref())


def defaults(
    window_ids: Collection[str],
    *,
    park: bool,
    record_audio: bool,
    default_windows: Collection[str] | None = None,
) -> AutopilotSettings:
    """First-run settings: everything on unless the environment narrowed the windows."""
    return AutopilotSettings(
        autopilot_enabled=True,
        park=park,
        record_audio=record_audio,
        windows={
            i: WindowPref(enabled=default_windows is None or i in default_windows)
            for i in window_ids
        },
    )


def to_json(s: AutopilotSettings) -> str:
    return json.dumps(
        {
            "autopilot_enabled": s.autopilot_enabled,
            "park": s.park,
            "record_audio": s.record_audio,
            "windows": {
                i: {
                    "enabled": w.enabled,
                    "receiver": w.receiver.model_dump(mode="json") if w.receiver else None,
                }
                for i, w in s.windows.items()
            },
        },
        sort_keys=True,
    )


def from_json(text: str | None, base: AutopilotSettings) -> AutopilotSettings:
    """Stored settings laid over ``base``. Garbage or unknown windows never raise."""
    if not text:
        return base
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        log.warning("stored GhostNet settings are not JSON; using defaults")
        return base
    if not isinstance(raw, dict):
        return base

    def flag(key: str, fallback: bool) -> bool:
        value = raw.get(key)
        return value if isinstance(value, bool) else fallback

    windows = dict(base.windows)
    stored = raw.get("windows")
    for window_id, entry in stored.items() if isinstance(stored, dict) else ():
        if window_id not in windows or not isinstance(entry, dict):
            continue  # a window the plan no longer has
        enabled = entry.get("enabled")
        receiver: ReceiverRef | None = None
        if entry.get("receiver") is not None:
            try:
                receiver = ReceiverRef.model_validate(entry["receiver"])
            except ValidationError:
                receiver = None
        windows[window_id] = WindowPref(
            enabled=enabled if isinstance(enabled, bool) else windows[window_id].enabled,
            receiver=receiver,
        )
    return AutopilotSettings(
        autopilot_enabled=flag("autopilot_enabled", base.autopilot_enabled),
        park=flag("park", base.park),
        record_audio=flag("record_audio", base.record_audio),
        windows=windows,
    )


def load(store: Store, base: AutopilotSettings) -> AutopilotSettings:
    return from_json(store.setting(KEY), base)


def save(store: Store, s: AutopilotSettings) -> None:
    store.save_setting(KEY, to_json(s))


def apply_update(current: AutopilotSettings, update: SetGhostNetSettings) -> AutopilotSettings:
    """``current`` with ``update`` applied. Raises SettingsError; never half-applies."""
    unknown = sorted(set(update.windows) - set(current.windows))
    if unknown:
        raise SettingsError(f"unknown window: {', '.join(unknown)}")
    windows = dict(current.windows)
    for window_id, change in update.windows.items():
        if change.receiver is not None and change.clear_receiver:
            raise SettingsError(f"{window_id}: give a receiver or clear it, not both")
        pref = windows[window_id]
        if change.enabled is not None:
            pref = replace(pref, enabled=change.enabled)
        if change.clear_receiver:
            pref = replace(pref, receiver=None)
        elif change.receiver is not None:
            pref = replace(pref, receiver=change.receiver)
        windows[window_id] = pref
    return AutopilotSettings(
        autopilot_enabled=(
            current.autopilot_enabled
            if update.autopilot_enabled is None
            else update.autopilot_enabled
        ),
        park=current.park if update.park is None else update.park,
        record_audio=(current.record_audio if update.record_audio is None else update.record_audio),
        windows=windows,
    )

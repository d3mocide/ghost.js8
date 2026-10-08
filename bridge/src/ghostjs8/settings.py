"""Bridge configuration from environment variables (see .env.example)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from ghostjs8.receivers.base import Mode, Tuning


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    listen_host: str = "0.0.0.0"  # noqa: S104 - container service on an internal network
    listen_port: int = 8073
    agent_url: str = "ws://decoder:8074/agent"
    allowed_origins: tuple[str, ...] = ()  # empty: allow any (put auth in front)
    max_clients: int = 16
    # Optional receiver to start listening on at boot (persistent listening).
    receiver_host: str | None = None
    receiver_port: int = 8073
    receiver_password: str = ""
    tuning: Tuning = field(default_factory=lambda: Tuning(dial_hz=14_078_000))
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env
        mode = e.get("GHOSTJS8_MODE", "usb").lower()
        if mode not in ("usb", "lsb"):
            raise ValueError(f"GHOSTJS8_MODE must be usb or lsb, not {mode!r}")
        typed_mode: Mode = "usb" if mode == "usb" else "lsb"
        origins = tuple(
            o.strip() for o in e.get("GHOSTJS8_ALLOWED_ORIGINS", "").split(",") if o.strip()
        )
        return cls(
            listen_host=e.get("GHOSTJS8_LISTEN_HOST", cls.listen_host),
            listen_port=_int(e, "GHOSTJS8_LISTEN_PORT", cls.listen_port),
            agent_url=e.get("GHOSTJS8_AGENT_URL", cls.agent_url),
            allowed_origins=origins,
            max_clients=_int(e, "GHOSTJS8_MAX_CLIENTS_PER_SESSION", cls.max_clients),
            receiver_host=e.get("GHOSTJS8_RECEIVER_HOST") or None,
            receiver_port=_int(e, "GHOSTJS8_RECEIVER_PORT", cls.receiver_port),
            receiver_password=e.get("GHOSTJS8_RECEIVER_PASSWORD", ""),
            tuning=Tuning(
                dial_hz=_int(e, "GHOSTJS8_DIAL_HZ", 14_078_000),
                mode=typed_mode,
                low_cut_hz=_int(e, "GHOSTJS8_LOW_CUT_HZ", 100),
                high_cut_hz=_int(e, "GHOSTJS8_HIGH_CUT_HZ", 3000),
            ),
            log_level=e.get("GHOSTJS8_LOG_LEVEL", "INFO").upper(),
        )

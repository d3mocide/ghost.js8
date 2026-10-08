"""A stand-in decoder-agent for UI development and browser tests.

Speaks the real agent protocol (``agent_protocol.py``): accepts PCM, reports
healthy, and emits *scripted* JS8Call messages on UTC 15 s boundaries. It
decodes nothing. Real decoding is proven only by ``make acceptance``.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from ghostjs8.decoders.base import DecoderHealth
from ghostjs8.decoders.js8call_native import agent_protocol as proto

log = logging.getLogger("ghostjs8.sim.fake_agent")

# (from, to or None, text after "FROM: ", grid, snr, offset)
SCRIPT: list[tuple[str, str | None, str, str, int, int]] = [
    ("K0OG", "KN4CRD", "KN4CRD SNR +02", "EN34", -20, 702),
    ("KG9B", "KN4CRD", "KN4CRD HEARTBEAT SNR -14", "EN52", -14, 521),
    ("KN4ZXG", None, "@HB HEARTBEAT FM16", "FM16", -24, 1866),
    ("W1GHZ", "@ALLCALL", "@ALLCALL CQ CQ CQ FN31", "FN31pr", -9, 1210),
    ("W4GHT", "@GSTFLASH", "@GSTFLASH DRILL DRILL DRILL - EXERCISE ONLY", "EM73", -7, 1450),
    ("KN4CRD", "@GHOSTNET", "@GHOSTNET CHECKING IN EM73", "EM73", -11, 980),
]


def _messages(i: int, now: datetime) -> list[dict[str, Any]]:
    frm, to, text, grid, snr, off = SCRIPT[i % len(SCRIPT)]
    utc = int(now.timestamp() * 1000)
    common = {
        "SNR": snr,
        "OFFSET": off,
        "SPEED": 0,
        "UTC": utc,
        "DIAL": 14_078_000,
        "FREQ": 14_078_000 + off,
    }
    out: list[dict[str, Any]] = [
        {"type": "RX.ACTIVITY", "value": f"{frm}: {text} ", "params": common},
    ]
    if to:
        out.append(
            {
                "type": "RX.DIRECTED",
                "value": f"{text} ♢ ",
                "params": {**common, "FROM": frm, "TO": to, "GRID": ""},
            }
        )
    out.append(
        {
            "type": "RX.CALL_ACTIVITY",
            "value": "",
            "params": {frm: {"SNR": snr, "GRID": grid, "UTC": utc}},
        }
    )
    return out


class FakeAgent:
    def __init__(self, period_s: float = 15.0) -> None:
        self._period = period_s
        self._last_pcm: datetime | None = None

    async def handle(self, ws: ServerConnection) -> None:
        log.info("bridge connected")
        sender = asyncio.create_task(self._send_loop(ws))
        try:
            async for message in ws:
                if isinstance(message, bytes):
                    self._last_pcm = datetime.now(UTC)
        except ConnectionClosed:
            pass
        finally:
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender

    async def _send_loop(self, ws: ServerConnection) -> None:
        i = 0
        next_cycle = 0.0
        loop = asyncio.get_running_loop()
        while True:
            now = datetime.now(UTC)
            health = DecoderHealth(
                process_up=True,
                capturing=True,
                last_ping_utc=now,
                last_api_reply_utc=now,
                last_audio_write_utc=self._last_pcm,
                details={"simulated": "true"},
            )
            await ws.send(proto.encode_health(health, now))
            if loop.time() >= next_cycle:
                if next_cycle:  # skip the very first tick so the UI starts empty
                    for msg in _messages(i, now):
                        await ws.send(proto.encode_js8(msg, now))
                    i += 1
                next_cycle = loop.time() + self._period
            await asyncio.sleep(1.0)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="ghost.js8 simulated decoder-agent (UI tests only)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=proto.DEFAULT_AGENT_PORT)
    p.add_argument("--period", type=float, default=15.0)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    agent = FakeAgent(args.period)

    async def run() -> None:
        async with serve(agent.handle, args.host, args.port, compression=None):
            await asyncio.Event().wait()

    asyncio.run(run())


if __name__ == "__main__":
    main()

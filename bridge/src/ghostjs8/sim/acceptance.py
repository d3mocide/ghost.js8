"""Acceptance client: connect to the browser-facing WebSocket like a browser and
wait for an expected decode. Exit 0 on success, 1 on timeout.

Mocked decodes cannot satisfy this: the text must come from native JS8Call
decoding the real upstream recording replayed through fake-kiwi.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

from websockets.asyncio.client import connect

from ghostjs8.contract.messages import Decode, Hello, server_message_adapter

EXPECTED = "K0OG: KN4CRD SNR +02"


async def wait_for_decode(url: str, expected: str, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            async with connect(url, open_timeout=5) as ws:
                print(f"[acceptance] connected to {url}", flush=True)
                async with asyncio.timeout(max(0.0, deadline - time.monotonic())):
                    async for raw in ws:
                        if isinstance(raw, bytes):
                            continue
                        msg = server_message_adapter.validate_python(json.loads(raw))
                        if isinstance(msg, Hello):
                            print(f"[acceptance] hello build={msg.build} v={msg.v}", flush=True)
                        elif isinstance(msg, Decode):
                            print(
                                f"[acceptance] decode {msg.kind} {msg.utc:%H:%M:%S} snr={msg.snr_db} off={msg.offset_hz} {msg.text}",
                                flush=True,
                            )
                            if expected in msg.text:
                                print(f"[acceptance] PASS: saw {expected!r}", flush=True)
                                return True
        except TimeoutError:
            break
        except OSError as exc:
            print(f"[acceptance] waiting for bridge: {exc}", flush=True)
            await asyncio.sleep(2)
    print(f"[acceptance] FAIL: {expected!r} not decoded within {timeout_s:.0f}s", flush=True)
    return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ghost.js8 real-recording acceptance test")
    p.add_argument("--url", default="ws://bridge:8073/ws")
    p.add_argument("--expect", default=EXPECTED)
    p.add_argument("--timeout", type=float, default=150.0)
    args = p.parse_args(argv)
    ok = asyncio.run(wait_for_decode(args.url, args.expect, args.timeout))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

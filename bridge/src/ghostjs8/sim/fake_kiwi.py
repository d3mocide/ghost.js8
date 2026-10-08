"""A simulated KiwiSDR speaking real SND / W/F / MSG framing.

Used by unit/integration tests and by the acceptance stack (tools/fake-kiwi).
It is a test double, not an emulator: it implements the subset of the protocol
the adapter relies on, plus fault injection.

Audio: plays a 12 kHz mono s16 WAV (or silence) as big-endian PCM frames,
paced in real time. Playback can be aligned to UTC 15 s boundaries and
repeated, which is what JS8 decoding needs.

Pairing: a W/F connection is accepted only while an SND connection with the
same session identifier is open; otherwise it gets ``MSG pairing_error`` and is
closed. (Real Kiwis associate the two by this identifier.)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import math
import struct
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

log = logging.getLogger("ghostjs8.sim.fake_kiwi")

RATE = 12_000
SAMPLES_PER_FRAME = 512
WF_BINS = 1024

Behavior = Literal["ok", "too_busy", "bad_password", "down", "db_update", "silent", "hang_up"]


@dataclass
class FakeKiwiConfig:
    host: str = "127.0.0.1"
    port: int = 0
    behavior: Behavior = "ok"
    password: str = ""  # if set, wrong passwords get badp=1
    audio_rate: int = RATE
    sample_rate: float = 12001.135
    little_endian_flag: bool = False  # send LE PCM with the LE flag set
    compressed_flag: bool = False  # mark every frame compressed (fault)
    stereo_flag: bool = False  # mark every frame stereo (fault)
    truncate_every: int = 0  # every Nth SND frame truncated (fault); 0 = never
    adc_overload: bool = False
    wav: Path | None = None
    align_utc_s: int = 0  # align playback starts to this boundary (15 for JS8); 0 = immediate
    repeats: int = 1
    repeat_gap_s: int = 15  # extra boundaries between repeats
    wf_rows_per_s: float = 10.0
    bandwidth_hz: int = 30_000_000


@dataclass
class _SessionLog:
    commands: list[str] = field(default_factory=list)


class FakeKiwi:
    def __init__(self, config: FakeKiwiConfig, *, now: Callable[[], float] = time.time) -> None:
        self.config = config
        self._now = now
        self._snd_sessions: set[int] = set()
        self.sessions: dict[tuple[int, str], _SessionLog] = {}
        self._server: Server | None = None
        self.port = config.port
        self._pcm = _load_wav(config.wav) if config.wav else b""

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        self._server = await serve(
            self._handle,
            self.config.host,
            self.config.port,
            process_request=self._process_request,
            compression=None,
            ping_interval=None,
        )
        sock = next(iter(self._server.sockets))
        self.port = sock.getsockname()[1]
        log.info(
            "fake kiwi listening on %s:%d (%s)", self.config.host, self.port, self.config.behavior
        )

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def __aenter__(self) -> FakeKiwi:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    def commands(self, stream: str) -> list[str]:
        """All SET commands received on a stream kind across sessions."""
        return [c for (sid, kind), s in self.sessions.items() if kind == stream for c in s.commands]

    # ------------------------------------------------------------- routing

    def _process_request(self, connection: ServerConnection, request: Request) -> Response | None:
        parts = request.path.strip("/").split("/")
        valid = (
            len(parts) in (2, 3) and parts[0].isdigit() and "/".join(parts[1:]) in ("SND", "W/F")
        )
        if not valid:
            return connection.respond(404, "not a kiwi stream\n")
        return None

    async def _handle(self, ws: ServerConnection) -> None:
        if ws.request is None:  # pragma: no cover - set before the handler runs
            return
        parts = ws.request.path.strip("/").split("/")
        sid, kind = int(parts[0]), "/".join(parts[1:])
        slog = self.sessions.setdefault((sid, kind), _SessionLog())
        try:
            if kind == "SND":
                self._snd_sessions.add(sid)
                try:
                    await self._snd(ws, slog)
                finally:
                    self._snd_sessions.discard(sid)
            else:
                await self._wf(ws, sid, slog)
        except ConnectionClosed:
            pass

    # ------------------------------------------------------------ handshake

    async def _auth(self, ws: ServerConnection, slog: _SessionLog) -> bool:
        cmd = await self._recv_cmd(ws, slog)
        if not cmd.startswith("SET auth"):
            await ws.close(1008, "expected auth")
            return False
        b = self.config.behavior
        if b == "hang_up":
            await ws.close(1011, "bye")
            return False
        if b == "silent":
            await ws.wait_closed()  # never answers; client must time out
            return False
        if b == "too_busy":
            await self._msg(ws, "too_busy=4")
            await ws.close()
            return False
        if b == "down":
            await self._msg(ws, "down")
            await ws.close()
            return False
        if b == "db_update":
            await self._msg(ws, "badp=6")
            await ws.close()
            return False
        given = cmd.partition(" p=")[2]
        if b == "bad_password" or (self.config.password and given != self.config.password):
            await self._msg(ws, "badp=1")
            await ws.close()
            return False
        await self._msg(ws, "badp=0")
        await self._msg(ws, "version_maj=1 version_min=826")
        await self._msg(ws, f"bandwidth={self.config.bandwidth_hz} rx_chans=8 chan_no_pwd=8")
        return True

    async def _recv_cmd(self, ws: ServerConnection, slog: _SessionLog) -> str:
        raw = await ws.recv()
        text = raw if isinstance(raw, str) else raw.decode()
        if text != "SET keepalive":
            slog.commands.append(text)
        return text

    async def _msg(self, ws: ServerConnection, body: str) -> None:
        await ws.send(b"MSG " + body.encode())

    # ----------------------------------------------------------------- SND

    async def _snd(self, ws: ServerConnection, slog: _SessionLog) -> None:
        if not await self._auth(ws, slog):
            return
        await self._msg(ws, f"audio_rate={self.config.audio_rate}")
        await self._msg(ws, f"sample_rate={self.config.sample_rate:.3f}")
        mod_seen = asyncio.Event()
        reader = asyncio.create_task(self._drain(ws, slog, on_mod=mod_seen.set))
        try:
            waiter = asyncio.create_task(mod_seen.wait())
            await asyncio.wait({waiter, reader}, return_when=asyncio.FIRST_COMPLETED)
            waiter.cancel()
            if mod_seen.is_set():
                await self._stream_audio(ws)
        finally:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader

    async def _drain(
        self, ws: ServerConnection, slog: _SessionLog, on_mod: Callable[[], None] | None = None
    ) -> None:
        async for raw in ws:
            text = raw if isinstance(raw, str) else raw.decode()
            if text == "SET keepalive":
                continue
            slog.commands.append(text)
            if on_mod and text.startswith("SET mod="):
                on_mod()

    def _playback_starts(self, t0: float) -> list[int]:
        """Sample indices (relative to stream start t0) where the WAV starts."""
        if not self._pcm:
            return []
        align = self.config.align_utc_s
        first = math.ceil((t0 + 0.5) / align) * align if align else t0
        step = (len(self._pcm) // 2) / RATE + (self.config.repeat_gap_s if align else 0)
        if align:
            step = math.ceil(step / align) * align
        return [round((first + i * step - t0) * RATE) for i in range(self.config.repeats)]

    async def _stream_audio(self, ws: ServerConnection) -> None:
        cfg = self.config
        t0 = self._now()
        starts = self._playback_starts(t0)
        wav_len = len(self._pcm) // 2
        flags = 0x02 if cfg.adc_overload else 0
        flags |= 0x80 if cfg.little_endian_flag else 0
        flags |= 0x10 if cfg.compressed_flag else 0
        flags |= 0x08 if cfg.stereo_flag else 0
        n = 0
        seq = 0
        loop = asyncio.get_running_loop()
        mono0 = loop.time()
        while True:
            samples = bytearray(SAMPLES_PER_FRAME * 2)  # native s16le assembly
            for start in starts:
                lo, hi = max(n, start), min(n + SAMPLES_PER_FRAME, start + wav_len)
                if lo < hi:
                    samples[(lo - n) * 2 : (hi - n) * 2] = self._pcm[
                        (lo - start) * 2 : (hi - start) * 2
                    ]
            pcm = bytes(samples) if cfg.little_endian_flag else _swap16(bytes(samples))
            header = b"SND" + struct.pack("<BI", flags, seq) + struct.pack(">H", 1270 - 600)
            frame = header + pcm
            seq += 1
            if cfg.truncate_every and seq % cfg.truncate_every == 0:
                frame = frame[:-1]
            await ws.send(frame)
            n += SAMPLES_PER_FRAME
            await asyncio.sleep(max(0.0, mono0 + n / RATE - loop.time()))

    # ----------------------------------------------------------------- W/F

    async def _wf(self, ws: ServerConnection, sid: int, slog: _SessionLog) -> None:
        if sid not in self._snd_sessions:
            await self._msg(ws, "pairing_error=no_snd_session")
            await ws.close(1008, "unpaired W/F")
            return
        if not await self._auth(ws, slog):
            return
        await self._msg(ws, "wf_setup")
        reader = asyncio.create_task(self._drain(ws, slog))
        try:
            seq = 0
            period = 1.0 / self.config.wf_rows_per_s
            while sid in self._snd_sessions:
                await ws.send(_synthetic_wf_row(seq, zoom=_last_zoom(slog), x_bin=0))
                seq += 1
                await asyncio.sleep(period)
            await ws.close()
        finally:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader


def _last_zoom(slog: _SessionLog) -> int:
    for cmd in reversed(slog.commands):
        if cmd.startswith("SET zoom="):
            return int(cmd.split()[1].split("=")[1])
    return 0


def _synthetic_wf_row(seq: int, *, zoom: int, x_bin: int) -> bytes:
    """Noise floor plus a slowly drifting carrier: enough to test transport/rendering."""
    floor = 255 - 110
    carrier = (seq * 3) % WF_BINS
    row = bytearray(floor + ((i * 7 + seq * 13) % 9) for i in range(WF_BINS))
    for d in range(-2, 3):
        row[(carrier + d) % WF_BINS] = 255 - 40 - abs(d) * 6
    return b"W/F" + b"\x00" + struct.pack("<III", x_bin, zoom & 0xFFFF, seq) + bytes(row)


def _swap16(pcm: bytes) -> bytes:
    out = bytearray(len(pcm))
    out[0::2] = pcm[1::2]
    out[1::2] = pcm[0::2]
    return bytes(out)


def _load_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, RATE):
            raise ValueError(f"{path}: need mono s16 at {RATE} Hz")
        return w.readframes(w.getnframes())  # little-endian s16


# ----------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Simulated KiwiSDR for ghost.js8 tests")
    p.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container service
    p.add_argument("--port", type=int, default=8073)
    p.add_argument("--wav", type=Path)
    p.add_argument("--align", type=int, default=15, help="UTC alignment seconds (0 = none)")
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--behavior", default="ok")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = FakeKiwiConfig(
        host=args.host,
        port=args.port,
        wav=args.wav,
        align_utc_s=args.align,
        repeats=args.repeats,
        behavior=args.behavior,
    )

    async def run() -> None:
        async with FakeKiwi(cfg):
            await asyncio.Event().wait()

    asyncio.run(run())


__all__ = ["FakeKiwi", "FakeKiwiConfig", "main"]

if __name__ == "__main__":
    main()

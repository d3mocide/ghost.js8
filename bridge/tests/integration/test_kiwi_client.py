"""KiwiReceiver against the fake KiwiSDR over real localhost sockets."""

from __future__ import annotations

import asyncio
import contextlib
import socket
import struct
import wave
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from websockets.asyncio.client import connect

from ghostjs8.receivers.base import (
    AudioBlock,
    ReceiverRejected,
    ReceiverTimeout,
    ReceiverUnreachable,
    RejectReason,
    Tuning,
    UnsupportedAudioFormat,
    WaterfallRow,
)
from ghostjs8.receivers.kiwisdr.client import KiwiEndpoint, KiwiReceiver
from ghostjs8.sim.fake_kiwi import FakeKiwi, FakeKiwiConfig

pytestmark = pytest.mark.integration

TUNING = Tuning(dial_hz=14_078_000, mode="usb", low_cut_hz=100, high_cut_hz=3000)


@dataclass
class Sink:
    audio: list[AudioBlock] = field(default_factory=list)
    rows: list[WaterfallRow] = field(default_factory=list)
    info: dict[str, str] = field(default_factory=dict)

    def on_audio(self, block: AudioBlock) -> None:
        self.audio.append(block)

    def on_waterfall(self, row: WaterfallRow) -> None:
        self.rows.append(row)

    def on_info(self, key: str, value: str) -> None:
        self.info[key] = value


@contextlib.asynccontextmanager
async def fake(**kw: object) -> AsyncIterator[FakeKiwi]:
    async with FakeKiwi(FakeKiwiConfig(**kw)) as kiwi:  # type: ignore[arg-type]
        yield kiwi


def receiver(kiwi: FakeKiwi, sink: Sink, **kw: object) -> KiwiReceiver:
    opts: dict[str, object] = {"handshake_timeout_s": 3.0, "connect_timeout_s": 3.0}
    opts.update(kw)
    return KiwiReceiver(KiwiEndpoint("127.0.0.1", kiwi.port), TUNING, sink, **opts)  # type: ignore[arg-type]


async def run_until(rx: KiwiReceiver, cond: object, timeout: float = 5.0) -> None:
    """Run the receiver until cond() is true, then close it cleanly."""
    task = asyncio.create_task(rx.run())
    try:
        async with asyncio.timeout(timeout):
            while not cond():  # type: ignore[operator]
                if task.done():
                    await task
                    return
                await asyncio.sleep(0.02)
    finally:
        await rx.close()
        await asyncio.wait_for(task, 3)


def tone_wav(path: Path, n: int = 12_000) -> list[int]:
    samples = [((i * 37) % 2000) - 1000 for i in range(n)]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(12_000)
        w.writeframes(struct.pack(f"<{n}h", *samples))
    return samples


# ----------------------------------------------------------------- happy path


async def test_streams_audio_and_waterfall(tmp_path: Path) -> None:
    samples = tone_wav(tmp_path / "t.wav")
    sink = Sink()
    async with fake(wav=tmp_path / "t.wav") as kiwi:
        rx = receiver(kiwi, sink)
        await run_until(rx, lambda: len(sink.audio) >= 30 and len(sink.rows) >= 2)

    pcm = b"".join(b.pcm_s16le for b in sink.audio)
    got = list(struct.unpack(f"<{len(pcm) // 2}h", pcm))
    assert got[: len(samples)] == samples[: len(got)]  # big-endian on the wire -> LE out
    assert all(not b.adc_overload for b in sink.audio)
    assert all(len(r.bins) == 1024 for r in sink.rows)
    assert sink.info["audio_rate"] == "12000"
    assert sink.info["version_maj"] == "1"


async def test_little_endian_flag_path(tmp_path: Path) -> None:
    samples = tone_wav(tmp_path / "t.wav")
    sink = Sink()
    async with fake(wav=tmp_path / "t.wav", little_endian_flag=True) as kiwi:
        await run_until(receiver(kiwi, sink, waterfall=False), lambda: len(sink.audio) >= 10)
    pcm = b"".join(b.pcm_s16le for b in sink.audio)
    assert list(struct.unpack(f"<{len(pcm) // 2}h", pcm)) == samples[: len(pcm) // 2]


async def test_sends_expected_commands_and_never_shared_hardware() -> None:
    sink = Sink()
    async with fake() as kiwi:
        await run_until(receiver(kiwi, sink), lambda: len(sink.rows) >= 1 and len(sink.audio) >= 1)
        snd, wf = kiwi.commands("SND"), kiwi.commands("W/F")
    assert "SET compression=0" in snd
    assert "SET mod=usb low_cut=100 high_cut=3000 freq=14078.000" in snd
    assert "SET ident_user=ghost.js8" in snd
    assert "SET wf_comp=0" in wf
    assert any(c.startswith("SET zoom=11 cf=14079.550") for c in wf)
    forbidden = ("attn", "rf_attn", "genattn", "SET gen=", "admin")
    assert not [c for c in snd + wf if any(f in c for f in forbidden)]


async def test_both_streams_use_one_session_id() -> None:
    sink = Sink()
    async with fake() as kiwi:
        rx = receiver(kiwi, sink, session_id=4242)
        await run_until(rx, lambda: len(sink.rows) >= 1)
        assert {sid for sid, _ in kiwi.sessions} == {4242}
        assert {kind for _, kind in kiwi.sessions} == {"SND", "W/F"}


async def test_unpaired_waterfall_is_refused_by_server() -> None:
    async with fake() as kiwi:
        async with connect(f"ws://127.0.0.1:{kiwi.port}/999/W/F") as ws:
            msg = await ws.recv()
        assert msg == b"MSG pairing_error=no_snd_session"


async def test_retune_sends_new_mod_and_view() -> None:
    sink = Sink()
    async with fake() as kiwi:
        rx = receiver(kiwi, sink)
        task = asyncio.create_task(rx.run())
        async with asyncio.timeout(5):
            while len(sink.rows) < 1:
                await asyncio.sleep(0.02)
        await rx.retune(Tuning(dial_hz=7_078_000, mode="lsb"))
        await asyncio.sleep(0.2)
        await rx.close()
        await asyncio.wait_for(task, 3)
        assert "SET mod=lsb low_cut=-3000 high_cut=-100 freq=7078.000" in kiwi.commands("SND")
        assert any(c.startswith("SET zoom=11 cf=7076.450") for c in kiwi.commands("W/F"))


async def test_adc_overload_flag_surfaces() -> None:
    sink = Sink()
    async with fake(adc_overload=True) as kiwi:
        await run_until(receiver(kiwi, sink, waterfall=False), lambda: len(sink.audio) >= 3)
    assert all(b.adc_overload for b in sink.audio)


async def test_truncated_frames_dropped_session_continues() -> None:
    sink = Sink()
    async with fake(truncate_every=3) as kiwi:
        rx = receiver(kiwi, sink, waterfall=False)
        await run_until(rx, lambda: len(sink.audio) >= 20)
    assert rx.stats["dropped_frames"] >= 5


# ------------------------------------------------------------------ rejections


@pytest.mark.parametrize(
    ("behavior", "reason"),
    [
        ("too_busy", RejectReason.FULL),
        ("bad_password", RejectReason.AUTH),
        ("down", RejectReason.DOWN),
        ("db_update", RejectReason.BUSY),
    ],
)
async def test_receiver_rejections(behavior: str, reason: RejectReason) -> None:
    async with fake(behavior=behavior) as kiwi:
        with pytest.raises(ReceiverRejected) as exc:
            await receiver(kiwi, Sink()).run()
    assert exc.value.reason is reason


async def test_wrong_password_rejected() -> None:
    async with fake(password="sekrit") as kiwi:
        with pytest.raises(ReceiverRejected) as exc:
            await receiver(kiwi, Sink()).run()
    assert exc.value.reason is RejectReason.AUTH


async def test_handshake_timeout() -> None:
    async with fake(behavior="silent") as kiwi:
        with pytest.raises(ReceiverTimeout):
            await receiver(kiwi, Sink(), handshake_timeout_s=0.5).run()


async def test_refused_port_is_unreachable() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]  # bound but not listening -> refused
        rx = KiwiReceiver(KiwiEndpoint("127.0.0.1", port), TUNING, Sink())
        with pytest.raises(ReceiverUnreachable):
            await rx.run()


async def test_unresolvable_host_is_unreachable() -> None:
    rx = KiwiReceiver(KiwiEndpoint("no-such-host.invalid", 8073), TUNING, Sink())
    with pytest.raises(ReceiverUnreachable):
        await rx.run()


async def test_connect_timeout() -> None:
    async def never(_: object) -> None:
        await asyncio.Event().wait()

    @contextlib.asynccontextmanager
    async def slow_connector(url: str, address: str | None = None) -> AsyncIterator[object]:
        await never(url)
        yield None  # pragma: no cover

    rx = KiwiReceiver(
        KiwiEndpoint("127.0.0.1", 1),
        TUNING,
        Sink(),
        connect_timeout_s=0.2,
        connector=slow_connector,  # type: ignore[arg-type]
    )
    with pytest.raises(ReceiverTimeout):
        await rx.run()


# -------------------------------------------------------- unsupported formats


async def test_persistent_compressed_audio_is_fatal() -> None:
    async with fake(compressed_flag=True) as kiwi:
        with pytest.raises(UnsupportedAudioFormat) as exc:
            await receiver(kiwi, Sink(), waterfall=False, compression_grace_s=0.0).run()
    assert exc.value.kind == "compressed"


async def test_stereo_audio_is_fatal() -> None:
    async with fake(stereo_flag=True) as kiwi:
        with pytest.raises(UnsupportedAudioFormat) as exc:
            await receiver(kiwi, Sink(), waterfall=False).run()
    assert exc.value.kind == "stereo"


async def test_wrong_audio_rate_is_fatal() -> None:
    async with fake(audio_rate=20250) as kiwi:
        with pytest.raises(UnsupportedAudioFormat) as exc:
            await receiver(kiwi, Sink(), waterfall=False).run()
    assert exc.value.kind == "sample_rate"


async def test_close_returns_cleanly_and_releases_sockets() -> None:
    sink = Sink()
    async with fake() as kiwi:
        rx = receiver(kiwi, sink)
        await run_until(rx, lambda: len(sink.rows) >= 1)  # raises if run() raised
        await asyncio.sleep(0.2)
        assert rx._snd is None
        assert rx._wf is None

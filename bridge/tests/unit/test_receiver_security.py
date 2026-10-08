"""Receiver address policy, origin check and connection politeness (pre-0.1.0 review)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import ClassVar

import pytest
from pydantic import ValidationError

from ghostjs8.api.app import origin_allowed
from ghostjs8.api.hub import Hub
from ghostjs8.contract.messages import SelectReceiver
from ghostjs8.receivers.address_policy import AddressPolicy, ReceiverAddressRefused
from ghostjs8.receivers.base import (
    ReceiverSink,
    ReceiverTimeout,
    ReceiverUnreachable,
    Tuning,
)
from ghostjs8.receivers.kiwisdr.client import KiwiEndpoint, KiwiReceiver
from ghostjs8.session.station import ReceiverTarget, Station, StationConfig
from ghostjs8.settings import Settings
from ghostjs8.util.backoff import Backoff
from ghostjs8.util.clock import ManualClock

PUBLIC = AddressPolicy()
LAN = AddressPolicy(allow_private=True)
DEV = AddressPolicy(allow_loopback=True)


def answers(*ips: str):  # type: ignore[no-untyped-def]
    async def resolver(host: str, port: int) -> list[str]:
        return list(ips)

    return resolver


# ------------------------------------------------------------ address policy


@pytest.mark.parametrize(
    "host",
    ["127.1", "2130706433", "0x7f000001", "0177.0.0.1", "localtest.me", "rebind.example"],
)
async def test_names_resolving_to_loopback_are_refused(host: str) -> None:
    # The string may look harmless; the resolved address decides.
    with pytest.raises(ReceiverAddressRefused):
        await PUBLIC.resolve(host, 8073, answers("127.0.0.1"))
    with pytest.raises(ReceiverAddressRefused):
        await LAN.resolve(host, 8073, answers("127.0.0.1"))


@pytest.mark.parametrize(
    ("ip", "public_ok", "lan_ok"),
    [
        ("1.1.1.1", True, True),
        ("2606:4700:4700::1111", True, True),
        ("192.168.1.20", False, True),
        ("10.0.0.5", False, True),
        ("172.18.0.3", False, True),  # a Docker network address
        ("100.64.0.1", False, True),  # CGNAT / tailnets: LAN-only
        ("fd00::1", False, True),
        ("127.0.0.1", False, False),
        ("::1", False, False),
        ("::ffff:127.0.0.1", False, False),  # IPv4-mapped loopback
        ("169.254.169.254", False, False),  # cloud metadata
        ("0.0.0.0", False, False),  # noqa: S104
        ("224.0.0.1", False, False),
        ("240.0.0.1", False, False),  # reserved
    ],
)
async def test_resolved_address_policy(ip: str, public_ok: bool, lan_ok: bool) -> None:
    for policy, ok in ((PUBLIC, public_ok), (LAN, lan_ok)):
        if ok:
            assert await policy.resolve("kiwi.example", 8073, answers(ip)) == ip
        else:
            with pytest.raises(ReceiverAddressRefused):
                await policy.resolve("kiwi.example", 8073, answers(ip))


async def test_mixed_answer_is_refused() -> None:
    with pytest.raises(ReceiverAddressRefused):
        await PUBLIC.resolve("kiwi.example", 8073, answers("1.1.1.1", "10.0.0.1"))


async def test_resolution_failure_is_refused() -> None:
    async def broken(host: str, port: int) -> list[str]:
        raise OSError("NXDOMAIN")

    with pytest.raises(ReceiverAddressRefused, match="cannot resolve"):
        await PUBLIC.resolve("nope.example", 8073, broken)
    with pytest.raises(ReceiverAddressRefused):
        await PUBLIC.resolve("empty.example", 8073, answers())


async def test_loopback_only_for_the_simulated_stack() -> None:
    assert await DEV.resolve("127.0.0.1", 8073) == "127.0.0.1"
    assert await DEV.resolve("fake-kiwi", 8073, answers("127.0.0.1")) == "127.0.0.1"
    with pytest.raises(ReceiverAddressRefused):
        await DEV.resolve("kiwi.example", 8073, answers("10.0.0.1"))  # still no LAN


def test_internal_names_refused_early() -> None:
    for host in ("localhost", "decoder", "bridge", "x.localhost", "bad host!"):
        with pytest.raises(ReceiverAddressRefused):
            LAN.check_host(host)


def test_settings_default_to_public_receivers_only() -> None:
    s = Settings.from_env({})
    assert s.receiver_policy == AddressPolicy(allow_private=False, allow_loopback=False)
    on = Settings.from_env(
        {"GHOSTJS8_ALLOW_PRIVATE_RECEIVERS": "true", "GHOSTJS8_ALLOW_LOOPBACK_RECEIVERS": "1"}
    )
    assert on.receiver_policy == AddressPolicy(allow_private=True, allow_loopback=True)


# ------------------------------------------------------------ kiwi client


def test_ipv6_literal_is_bracketed() -> None:
    url = KiwiEndpoint("2606:4700::1111", 8073).stream_url(1, "SND")
    assert url == "ws://[2606:4700::1111]:8073/1/SND"
    assert KiwiEndpoint("kiwi.example").stream_url(1, "SND") == "ws://kiwi.example:8073/1/SND"


class _Sink:
    def on_audio(self, block: object) -> None: ...
    def on_waterfall(self, row: object) -> None: ...
    def on_receiver_info(self, info: object) -> None: ...
    def on_smeter(self, rssi: object) -> None: ...


async def test_client_dials_the_checked_address_and_refuses_bad_ones() -> None:
    dialed: list[tuple[str, str | None]] = []

    @contextlib.asynccontextmanager
    async def connector(url: str, address: str | None) -> AsyncIterator[object]:
        dialed.append((url, address))
        raise OSError("stop here")
        yield  # pragma: no cover

    class Policy(AddressPolicy):
        async def resolve(self, host: str, port: int, resolver: object = None) -> str:  # type: ignore[override]
            return await AddressPolicy.resolve(self, host, port, answers("93.184.216.34"))

    rx = KiwiReceiver(
        KiwiEndpoint("kiwi.example", 8073, policy=Policy()),
        Tuning(dial_hz=14_078_000),
        _Sink(),  # type: ignore[arg-type]
        connector=connector,  # type: ignore[arg-type]
        session_id=7,
    )
    with pytest.raises(ReceiverUnreachable):
        await rx.run()
    # URL keeps the name (Host header / SNI); TCP goes to the checked address.
    assert dialed == [("ws://kiwi.example:8073/7/SND", "93.184.216.34")]

    class Internal(AddressPolicy):
        async def resolve(self, host: str, port: int, resolver: object = None) -> str:  # type: ignore[override]
            return await AddressPolicy.resolve(self, host, port, answers("10.1.2.3"))

    dialed.clear()
    rx = KiwiReceiver(
        KiwiEndpoint("kiwi.example", 8073, policy=Internal()),
        Tuning(dial_hz=14_078_000),
        _Sink(),  # type: ignore[arg-type]
        connector=connector,  # type: ignore[arg-type]
    )
    with pytest.raises(ReceiverAddressRefused):
        await rx.run()
    assert dialed == []  # never dialed


# ------------------------------------------------------------ origin check


@pytest.mark.parametrize(
    ("origin", "host", "allowed", "ok"),
    [
        (None, "ghost.example", (), True),  # not a browser page
        ("https://ghost.example", "ghost.example", (), True),  # same origin
        ("http://127.0.0.1:4173", "127.0.0.1:4173", (), True),
        ("https://evil.example", "ghost.example", (), False),  # cross-site page
        ("https://ghost.example", None, (), False),
        ("http://192.168.1.5:8080", "192.168.1.5:8080", (), True),  # LAN, explicit port
        ("https://ghost.example", "ghost.example:443", (), True),  # default port spelled out
        ("http://ghost.example:8080", "ghost.example", (), False),  # port differs
        ("http://[fd00::5]:8080", "[fd00::5]:8080", (), True),
        ("https://a.example", "ghost.example", ("https://a.example",), True),
        ("https://ghost.example", "ghost.example", ("https://a.example",), False),
    ],
)
def test_origin_allowed(
    origin: str | None, host: str | None, allowed: tuple[str, ...], ok: bool
) -> None:
    assert origin_allowed(origin, host, allowed) is ok


# ------------------------------------------------------------ contract


@pytest.mark.parametrize("password", ["a b", "x\nSET mod=am", "tab\there", "\x00"])
def test_password_cannot_smuggle_parameters(password: str) -> None:
    with pytest.raises(ValidationError):
        SelectReceiver(receiver={"host": "kiwi.example", "port": 8073}, password=password)  # type: ignore[arg-type]
    SelectReceiver(receiver={"host": "kiwi.example", "port": 8073}, password="s3cr3t!#")  # type: ignore[arg-type]


# ------------------------------------------------------------ station politeness


class _Decoder:
    connected = True

    def __init__(self, sink: object) -> None: ...
    def submit_audio(self, pcm: bytes) -> None: ...

    async def run(self) -> None:
        await asyncio.Event().wait()

    async def close(self) -> None: ...


class _Rx:
    instances: ClassVar[list[_Rx]] = []
    fail: ClassVar[Exception | None] = None

    def __init__(self, target: ReceiverTarget, tuning: Tuning, sink: ReceiverSink) -> None:
        self.target = target
        self.closed = asyncio.Event()
        _Rx.instances.append(self)

    async def run(self) -> None:
        if _Rx.fail is not None:
            raise _Rx.fail
        await self.closed.wait()

    async def close(self) -> None:
        self.closed.set()

    async def retune(self, tuning: Tuning) -> None: ...


@pytest.fixture(autouse=True)
def _reset() -> None:
    _Rx.instances = []
    _Rx.fail = None


def _station(floor: float) -> Station:
    return Station(
        Hub(),
        _Decoder,  # type: ignore[arg-type]
        _Rx,  # type: ignore[arg-type]
        clock=ManualClock(),
        receiver_backoff=Backoff(minimum_s=0.01, maximum_s=0.02, jitter=0.0),
        config=StationConfig(min_connect_interval_s=floor),
    )


async def _until(cond: object, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not cond():  # type: ignore[operator]
            await asyncio.sleep(0.005)


async def test_reselect_burst_connects_only_the_latest_after_the_floor() -> None:
    st = _station(0.3)
    task = asyncio.create_task(st.run())
    try:
        st.select_receiver(ReceiverTarget("a.example", 8073))
        await _until(lambda: len(_Rx.instances) == 1)
        for host in ("b.example", "c.example", "d.example"):  # a viewer spamming selects
            st.select_receiver(ReceiverTarget(host, 8073))
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.1)
        assert len(_Rx.instances) == 1  # nothing new inside the floor
        await _until(lambda: len(_Rx.instances) == 2)
        assert _Rx.instances[1].target.host == "d.example"  # only the latest choice
    finally:
        task.cancel()


async def test_address_refusal_is_terminal_and_errors_are_coarse() -> None:
    _Rx.fail = ReceiverAddressRefused("receiver address is not allowed")
    st = _station(0)
    task = asyncio.create_task(st.run())
    try:
        st.select_receiver(ReceiverTarget("x.example", 8073))
        await _until(lambda: st.state == "failed")
        await asyncio.sleep(0.05)
        assert len(_Rx.instances) == 1  # not retried
    finally:
        task.cancel()

    for exc, detail in (
        (
            ReceiverUnreachable("ws://10.0.0.1:22/1/SND: [Errno 111] Connection refused"),
            "unreachable",
        ),
        (ReceiverTimeout("connect to ws://10.0.0.1:8080/1/SND timed out"), "in time"),
    ):
        _Rx.instances, _Rx.fail = [], exc
        st = _station(0)
        task = asyncio.create_task(st.run())
        try:
            st.select_receiver(ReceiverTarget("x.example", 8073))
            await _until(lambda st=st: st.state == "backoff")  # type: ignore[misc]
            assert detail in st.detail
            assert "10.0.0.1" not in st.detail
            assert "Errno" not in st.detail
        finally:
            task.cancel()

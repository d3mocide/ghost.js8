"""``python -m ghostjs8 <command>``: bridge, agent, fake-kiwi, acceptance."""

from __future__ import annotations

import sys


def _bridge() -> None:
    import uvicorn

    from ghostjs8.api.app import create_app
    from ghostjs8.api.hub import Hub
    from ghostjs8.decoders.base import DecoderSink
    from ghostjs8.decoders.js8call_native.adapter import Js8CallNativeDecoder
    from ghostjs8.receivers.base import ReceiverSink, Tuning
    from ghostjs8.receivers.kiwisdr.client import KiwiEndpoint, KiwiReceiver
    from ghostjs8.session.station import (
        DecoderHandle,
        ReceiverHandle,
        ReceiverTarget,
        Station,
        StationConfig,
    )
    from ghostjs8.settings import Settings
    from ghostjs8.store.sqlite import Store
    from ghostjs8.util.clock import SystemClock
    from ghostjs8.util.logs import configure

    settings = Settings.from_env()
    configure("bridge", settings.log_level, settings.log_format)
    clock = SystemClock()

    def make_receiver(target: ReceiverTarget, tuning: Tuning, sink: ReceiverSink) -> ReceiverHandle:
        return KiwiReceiver(
            KiwiEndpoint(target.host, target.port, target.password), tuning, sink, clock=clock
        )

    def make_decoder(sink: DecoderSink) -> DecoderHandle:
        return Js8CallNativeDecoder(settings.agent_url, sink, clock=clock)

    target = (
        ReceiverTarget(settings.receiver_host, settings.receiver_port, settings.receiver_password)
        if settings.receiver_host
        else None
    )
    station = Station(
        Hub(max_clients=settings.max_clients),
        make_decoder,
        make_receiver,
        tuning=settings.tuning,
        target=target,
        store=Store(settings.db_path, clock, retention_days=settings.retention_days)
        if settings.db_path
        else None,
        clock=clock,
        config=StationConfig(
            waterfall_max_fps=settings.waterfall_max_fps,
            idle_disconnect_s=settings.idle_disconnect_minutes * 60.0,
        ),
    )
    uvicorn.run(
        create_app(station, settings, clock=clock),
        host=settings.listen_host,
        port=settings.listen_port,
        log_config=None,
        access_log=False,
        ws_max_size=64 * 1024,
    )


def main() -> None:
    cmd, rest = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("", [])
    if cmd == "bridge":
        _bridge()
    elif cmd == "agent":
        from ghostjs8.decoders.js8call_native.agent import main as agent_main

        agent_main(rest)
    elif cmd == "fake-kiwi":
        from ghostjs8.sim.fake_kiwi import main as fake_main

        fake_main(rest)
    elif cmd == "acceptance":
        from ghostjs8.sim.acceptance import main as acceptance_main

        sys.exit(acceptance_main(rest))
    else:
        sys.stderr.write("usage: python -m ghostjs8 {bridge|agent|fake-kiwi|acceptance} [args]\n")
        sys.exit(2)


if __name__ == "__main__":
    main()

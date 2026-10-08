"""``python -m ghostjs8 <command>``: bridge, agent, fake-kiwi, acceptance."""

from __future__ import annotations

import logging
import sys


def _bridge() -> None:
    import uvicorn

    from ghostjs8.api.app import create_app
    from ghostjs8.api.hub import Hub
    from ghostjs8.decoders.js8call_native.adapter import Js8CallNativeDecoder
    from ghostjs8.receivers.base import ReceiverSink
    from ghostjs8.receivers.kiwisdr.client import KiwiEndpoint, KiwiReceiver
    from ghostjs8.session.station import ReceiverFactory, ReceiverHandle, Station
    from ghostjs8.settings import Settings

    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    receiver_factory: ReceiverFactory | None = None
    if settings.receiver_host:
        endpoint = KiwiEndpoint(
            settings.receiver_host, settings.receiver_port, settings.receiver_password
        )

        def make_receiver(sink: ReceiverSink) -> ReceiverHandle:
            return KiwiReceiver(endpoint, settings.tuning, sink)

        receiver_factory = make_receiver

    station = Station(
        Hub(max_clients=settings.max_clients),
        lambda sink: Js8CallNativeDecoder(settings.agent_url, sink),
        receiver_factory,
    )
    uvicorn.run(
        create_app(station, settings),
        host=settings.listen_host,
        port=settings.listen_port,
        log_level=settings.log_level.lower(),
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

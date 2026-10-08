"""Which receiver addresses the bridge may connect to on someone else's behalf.

Viewers (and the GhostNet autopilot, via the public directory) choose receiver
hosts. Without care that is a server-side request primitive: ``127.1``,
``0x7f000001``, a name that resolves to an internal address, or a DNS answer that
changes between check and connect would all reach things the bridge can see.

So the policy is enforced where the connection is made:

1. the host *string* is syntax-checked (a cheap, early, friendly error);
2. the name is resolved, **every** returned address is checked, and the
   connection is then made to that checked address (the URL keeps the name, so
   the HTTP Host header and TLS SNI are unchanged). Nothing re-resolves later,
   which closes DNS rebinding.

Receivers configured by the operator (``GHOSTJS8_RECEIVER_HOST``) are trusted
and bypass the policy.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ghostjs8.receivers.base import ReceiverError

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], Awaitable[list[str]]]

_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.?$"
)
# Names that only make sense inside the compose network.
_BLOCKED_NAMES = frozenset({"localhost", "decoder", "bridge", "web", "fake-kiwi"})


class ReceiverAddressRefused(ReceiverError):
    """The receiver host or one of its addresses is not allowed. Not retried."""


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    )
    return [str(info[4][0]) for info in infos]


@dataclass(frozen=True, slots=True)
class AddressPolicy:
    allow_private: bool = False
    #: Simulated/dev stacks only: lets the fake KiwiSDR on 127.0.0.1 be chosen.
    allow_loopback: bool = False

    def check_host(self, host: str) -> str:
        """Normalize and syntax-check a host string; refuse obvious internal names."""
        h = host.strip().rstrip(".").lower()
        literal = h[1:-1] if h.startswith("[") and h.endswith("]") else h
        try:
            ip = ipaddress.ip_address(literal)
        except ValueError:
            internal = h in _BLOCKED_NAMES or h.endswith(".localhost")
            if not _HOSTNAME.match(h) or (internal and not self.allow_loopback):
                raise ReceiverAddressRefused(f"not an allowed receiver host: {host!r}") from None
            return h
        self.check_ip(ip)
        return str(ip)

    def check_ip(self, ip: IPAddress) -> None:
        mapped = ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) else None
        if mapped is not None:
            ip = mapped
        if ip.is_loopback and self.allow_loopback:
            return
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            raise ReceiverAddressRefused("receiver address is not allowed")
        if ip.is_global:
            return
        if not self.allow_private or ip.is_reserved:
            raise ReceiverAddressRefused(
                "receiver resolves to a private address "
                "(set GHOSTJS8_ALLOW_PRIVATE_RECEIVERS=true for LAN receivers)"
            )

    async def resolve(self, host: str, port: int, resolver: Resolver = system_resolver) -> str:
        """Resolve ``host`` and return one address that the policy allows.

        Every address in the answer must pass; a mixed answer (one public, one
        internal) is refused rather than trusted.
        """
        name = self.check_host(host)
        try:
            ip = ipaddress.ip_address(name)
        except ValueError:
            pass
        else:
            return str(ip)
        try:
            answers = await resolver(name, port)
        except OSError as exc:
            raise ReceiverAddressRefused(f"cannot resolve receiver host {host!r}") from exc
        if not answers:
            raise ReceiverAddressRefused(f"cannot resolve receiver host {host!r}")
        addresses = [ipaddress.ip_address(a.split("%", 1)[0]) for a in answers]
        for a in addresses:
            self.check_ip(a)
        return str(addresses[0])


__all__ = ["AddressPolicy", "ReceiverAddressRefused", "Resolver", "system_resolver"]

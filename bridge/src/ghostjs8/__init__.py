"""ghost.js8 — receive-only JS8Call decoding through KiwiSDR receivers."""

from importlib.metadata import PackageNotFoundError, version
from typing import Final

try:
    __version__: str = version("ghostjs8")
except PackageNotFoundError:  # pragma: no cover - only when run from an unpacked tree
    __version__ = "0.0.0+unknown"

# Bridge <-> browser protocol version. Bump on any breaking contract change.
PROTOCOL_VERSION: Final = 1

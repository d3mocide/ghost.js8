"""Fan-out from one station to many browsers with bounded per-client queues.

JSON events go to every client. Binary audio / waterfall frames go only to
clients that subscribed to that channel. Queues drop the oldest item when full
so a slow viewer never adds latency for anyone else.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

log = logging.getLogger("ghostjs8.api.hub")

Outgoing = str | bytes
BinaryChannel = Literal["audio", "waterfall"]


class HubFull(Exception):
    """Too many browser clients for this session."""


@dataclass(eq=False)
class Client:
    queue: asyncio.Queue[Outgoing]
    audio: bool = False
    waterfall: bool = False
    dropped: int = 0
    closed: asyncio.Event = field(default_factory=asyncio.Event)

    def send(self, payload: Outgoing) -> None:
        if self.queue.full():
            self.dropped += 1
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()  # drop oldest, keep the stream live
        self.queue.put_nowait(payload)

    def send_model(self, message: BaseModel) -> None:
        self.send(message.model_dump_json())


class Hub:
    def __init__(self, *, max_clients: int = 16, queue_size: int = 256) -> None:
        self._clients: set[Client] = set()
        self._max_clients = max_clients
        self._queue_size = queue_size

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def max_clients(self) -> int:
        return self._max_clients

    def wants(self, channel: BinaryChannel) -> bool:
        return any(getattr(c, channel) for c in self._clients)

    def add(self) -> Client:
        if len(self._clients) >= self._max_clients:
            raise HubFull(f"session already has {self._max_clients} clients")
        client = Client(asyncio.Queue(maxsize=self._queue_size))
        self._clients.add(client)
        return client

    def remove(self, client: Client) -> None:
        self._clients.discard(client)
        client.closed.set()

    def broadcast(self, message: BaseModel) -> None:
        self.broadcast_raw(message.model_dump_json())

    def broadcast_raw(self, payload: Outgoing) -> None:
        for client in list(self._clients):
            client.send(payload)

    def broadcast_binary(self, channel: BinaryChannel, frame: bytes) -> None:
        for client in list(self._clients):
            if getattr(client, channel):
                client.send(frame)

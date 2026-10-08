"""Fan-out from one station to many browsers with bounded per-client queues."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field

from pydantic import BaseModel

log = logging.getLogger("ghostjs8.api.hub")

Outgoing = str | bytes


class HubFull(Exception):
    """Too many browser clients for this session."""


@dataclass(eq=False)
class Client:
    queue: asyncio.Queue[Outgoing]
    dropped: int = 0
    closed: asyncio.Event = field(default_factory=asyncio.Event)


class Hub:
    def __init__(self, *, max_clients: int = 16, queue_size: int = 256) -> None:
        self._clients: set[Client] = set()
        self._max_clients = max_clients
        self._queue_size = queue_size

    @property
    def client_count(self) -> int:
        return len(self._clients)

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
            if client.queue.full():
                client.dropped += 1
                with contextlib.suppress(asyncio.QueueEmpty):
                    client.queue.get_nowait()  # drop oldest, keep the stream live
            client.queue.put_nowait(payload)

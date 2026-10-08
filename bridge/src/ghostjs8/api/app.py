"""HTTP + WebSocket API for browsers."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from ghostjs8 import __version__
from ghostjs8.api.hub import HubFull
from ghostjs8.contract.messages import Hello
from ghostjs8.session.station import Station
from ghostjs8.settings import Settings

log = logging.getLogger("ghostjs8.api")


def create_app(station: Station, settings: Settings) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(station.run(), name="station")
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="ghost.js8 bridge", version=__version__, lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        origin = ws.headers.get("origin")
        if settings.allowed_origins and origin not in settings.allowed_origins:
            await ws.close(code=1008, reason="origin not allowed")
            return
        try:
            client = station.hub.add()
        except HubFull:
            await ws.close(code=1013, reason="session full")
            return
        await ws.accept()
        try:
            await ws.send_text(Hello(build=__version__).model_dump_json())
            async with asyncio.TaskGroup() as tg:
                tg.create_task(_pump_out(ws, client.queue))
                tg.create_task(_drain_in(ws))
        except* (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            station.hub.remove(client)

    return app


async def _pump_out(ws: WebSocket, queue: asyncio.Queue[str | bytes]) -> None:
    while True:
        item = await queue.get()
        if isinstance(item, bytes):
            await ws.send_bytes(item)
        else:
            await ws.send_text(item)


async def _drain_in(ws: WebSocket) -> None:
    while True:
        message = await ws.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(code=message.get("code", 1000))

"""HTTP routes for recorded GhostNet windows."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from ghostjs8.contract.messages import NetLog
from ghostjs8.ghostnet.recorder import OFFSET_HI_HZ, OFFSET_LO_HZ, net_stations
from ghostjs8.store.sqlite import Store

# Net ids are generated as "<window id>-YYYYMMDDTHHMMZ". Anything else is refused
# before it can touch the filesystem.
NET_ID = re.compile(r"^[a-z0-9-]{1,40}-\d{8}T\d{4}Z$")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def png_height(path: Path) -> int:
    try:
        with path.open("rb") as f:
            header = f.read(24)
    except OSError:
        return 0
    return int.from_bytes(header[20:24], "big") if header[:8] == PNG_MAGIC else 0


def nets_router(store: Store | None, recordings: Path) -> APIRouter:
    router = APIRouter(prefix="/api/nets")

    def checked(net_id: str) -> Store:
        if store is None or not NET_ID.match(net_id):
            raise HTTPException(status_code=404, detail="no such net")
        return store

    def file(path: Path, media_type: str) -> FileResponse:
        if not path.is_file():
            raise HTTPException(status_code=404, detail="not recorded")
        return FileResponse(path, media_type=media_type, filename=path.name)

    @router.get("")
    async def list_nets() -> JSONResponse:
        nets = store.nets() if store is not None else []
        return JSONResponse([json.loads(n.model_dump_json()) for n in nets])

    @router.get("/{net_id}")
    async def get_net(net_id: str) -> JSONResponse:
        st = checked(net_id)
        summary = st.net(net_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="no such net")
        decodes = st.net_decodes(net_id)
        body = NetLog(
            summary=summary,
            decodes=decodes,
            stations=net_stations(st, decodes),
            waterfall_seconds=png_height(recordings / net_id / "waterfall.png"),
            waterfall_offset_lo_hz=OFFSET_LO_HZ,
            waterfall_offset_hi_hz=OFFSET_HI_HZ,
        )
        return JSONResponse(json.loads(body.model_dump_json()))

    @router.get("/{net_id}/waterfall.png")
    async def get_waterfall(net_id: str) -> FileResponse:
        checked(net_id)
        return file(recordings / net_id / "waterfall.png", "image/png")

    @router.get("/{net_id}/audio.flac")
    async def get_audio(net_id: str) -> FileResponse:
        checked(net_id)
        return file(recordings / net_id / "audio.flac", "audio/flac")

    return router

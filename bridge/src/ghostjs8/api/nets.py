"""HTTP routes for recorded GhostNet windows."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from ghostjs8.contract.messages import NetLog, NetSummary
from ghostjs8.ghostnet.recorder import FLASH, OFFSET_HI_HZ, OFFSET_LO_HZ, net_stations
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


def live_summary(store: Store, recordings: Path, summary: NetSummary) -> NetSummary:
    """A net still being recorded only has its counts written at ``finish()``.

    Fill them from the store so the UI shows the traffic as it arrives.
    """
    if summary.ended is not None:
        return summary
    decodes = store.net_decodes(summary.id)
    audio = recordings / summary.id / "audio.flac"
    return summary.model_copy(
        update={
            "decode_count": len(decodes),
            "station_count": len(net_stations(store, decodes)),
            "flash_count": sum(1 for d in decodes if FLASH.search(d.text)),
            "has_audio": audio.is_file() and audio.stat().st_size > 0,
        }
    )


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
        nets = (
            [live_summary(store, recordings, n) for n in store.nets()] if store is not None else []
        )
        return JSONResponse([json.loads(n.model_dump_json()) for n in nets])

    @router.get("/{net_id}")
    async def get_net(net_id: str) -> JSONResponse:
        st = checked(net_id)
        summary = st.net(net_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="no such net")
        decodes = st.net_decodes(net_id)
        body = NetLog(
            summary=live_summary(st, recordings, summary),
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

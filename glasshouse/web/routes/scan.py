"""Live scan page showing nearby BLE devices."""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from glasshouse import vendors as vendor_db
from glasshouse.scanner.ble import get_nearby_devices

log = logging.getLogger(__name__)
router = APIRouter(prefix="/scan")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _categorise(devices: list[dict]) -> dict:
    matched = []
    interesting = []
    everything_else = []

    for d in devices:
        mfr = d.get("manufacturer", "Unknown")
        name = d.get("name", "")

        is_alert = vendor_db.has_enabled_oui(d.get("mac", ""))

        if is_alert:
            matched.append(d)
        elif mfr in ("Unknown", "Randomised") and name:
            # Unknown or randomised manufacturer with a name.
            interesting.append(d)
        else:
            everything_else.append(d)

    return {
        "matched": matched,
        "interesting": interesting,
        "everything_else": everything_else,
    }


def _scan_context() -> dict:
    devices = get_nearby_devices()
    categories = _categorise(devices)
    return {**categories, "total": len(devices)}


@router.get("/", response_class=HTMLResponse)
async def scan_page(request: Request):
    context = _scan_context()
    return templates.TemplateResponse(
        request,
        "scan.html",
        context,
    )


@router.get("/events")
async def scan_events():
    async def event_stream():
        last_payload = None
        idle_seconds = 0
        while True:
            payload = json.dumps(_scan_context(), separators=(",", ":"))
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
                idle_seconds = 0
            elif idle_seconds >= 15:
                yield ": keepalive\n\n"
                idle_seconds = 0
            await asyncio.sleep(1)
            idle_seconds += 1

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api")
async def scan_api():
    """JSON endpoint for the live scan data."""
    devices = get_nearby_devices()
    return _categorise(devices)

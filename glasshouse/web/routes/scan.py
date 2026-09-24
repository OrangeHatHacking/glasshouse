"""Live scan page showing nearby BLE devices."""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from glasshouse.scanner.ble import get_nearby_devices

log = logging.getLogger(__name__)
router = APIRouter(prefix="/scan")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# Manufacturers that are surveillance-relevant (from vendors.py)
ALERT_MANUFACTURERS = {
    "Ring", "DJI", "Axon", "Sepura", "Motorola Solutions",
    "Axon Enterprise, Inc.",          # IEEE registered name
    "Sepura Limited",                 # IEEE registered name
    "Motorola Solutions Inc.",        # IEEE registered name
    "Ring LLC",                       # IEEE registered name
    "SZ DJI Technology Co.,Ltd",      # IEEE registered name
}


def _categorise(devices: list[dict]) -> dict:
    matched = []
    interesting = []
    everything_else = []

    for d in devices:
        mfr = d.get("manufacturer", "Unknown")
        name = d.get("name", "")

        # Check alert list (case-insensitive partial match)
        is_alert = any(a.lower() in mfr.lower() for a in ALERT_MANUFACTURERS) if mfr not in ("Unknown", "Randomised") else False

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


@router.get("/", response_class=HTMLResponse)
async def scan_page(request: Request):
    devices = get_nearby_devices()
    cats = _categorise(devices)
    return templates.TemplateResponse(
        request, "scan.html", {
            "matched": cats["matched"],
            "interesting": cats["interesting"],
            "everything_else": cats["everything_else"],
            "total": len(devices),
        }
    )


@router.get("/api")
async def scan_api():
    """JSON endpoint for the live scan data."""
    devices = get_nearby_devices()
    return _categorise(devices)

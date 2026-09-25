"""Dashboard routes for detection history and status."""

import logging
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from glasshouse.storage import db

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
WINDOWS = {
    "10m": timedelta(minutes=10),
    "1h": timedelta(hours=1),
    "today": timedelta(days=1),
    "week": timedelta(days=7),
}


def _time_parts(value: str) -> tuple[str, str, str]:
    timestamp = datetime.fromisoformat(value)
    return (
        timestamp.strftime("%H:%M"),
        timestamp.strftime("%H:%M:%S"),
        timestamp.strftime("%d/%m/%Y"),
    )


def _match_label(match_type: str | None) -> str:
    labels = {
        "oui": "OUI",
        "mac": "MAC",
        "cid": "CID",
        "uuid": "UUID",
        "name": "NAME",
        "composite": "COMP",
    }
    if match_type in labels:
        return labels[match_type]
    if match_type and match_type.startswith("custom:"):
        return "Custom<br>" + match_type.split(":", 1)[1].upper()
    return match_type or "Unknown"


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, window: str = "today", sort: str = "last_seen"):
    window = window if window in WINDOWS or window == "all" else "today"
    sort = sort if sort in ("first_seen", "last_seen") else "last_seen"
    since = None
    if window != "all":
        since = (datetime.now(timezone.utc) - WINDOWS[window]).isoformat()
    detections = await db.get_latest_detections(limit=500, since=since, sort_by=sort)
    for detection in detections:
        detection["match_label"] = _match_label(detection.get("match_type"))
        detection["first_time"], detection["first_seconds"], detection["first_date"] = (
            _time_parts(detection["first_seen"])
        )
        detection["last_time"], detection["last_seconds"], detection["last_date"] = (
            _time_parts(detection["last_seen"])
        )
        try:
            manufacturer_data = json.loads(detection.get("manufacturer_data") or "{}")
            detection["company_ids"] = [
                hex(int(company_id)) for company_id in manufacturer_data
            ]
        except (TypeError, ValueError, json.JSONDecodeError):
            detection["company_ids"] = []
        try:
            detection["service_uuid_list"] = json.loads(
                detection.get("service_uuids") or "[]"
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            detection["service_uuid_list"] = []
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"detections": detections, "window": window, "sort": sort},
    )


@router.get("/api/detections")
async def api_detections(limit: int = 50, offset: int = 0):
    return await db.get_detections(limit=limit, offset=offset)


@router.get("/api/status")
async def api_status():
    """Lightweight status ping for the web UI."""
    return {"status": "scanning", "version": "0.1.0"}

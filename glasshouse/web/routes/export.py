"""Routes for exporting detection data."""

import io
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from glasshouse.storage import db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/export")


@router.get("/detections.json")
async def export_json():
    detections = await db.get_detections(limit=10000)
    content = json.dumps(detections, indent=2, default=str)
    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f"attachment; filename=glasshouse-detections-"
                f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
            )
        },
    )


@router.get("/gpx")
async def export_gpx():
    """Return empty GPX until GPS support is enabled."""
    gpx_content = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Glasshouse"
     xmlns="http://www.topografix.com/GPX/1/1">
  <!-- GPS not yet enabled. Enable GPS module and this endpoint will
       return detections as GPX waypoints with coordinates. -->
</gpx>"""
    return StreamingResponse(
        io.BytesIO(gpx_content.encode()),
        media_type="application/gpx+xml",
        headers={"Content-Disposition": "attachment; filename=glasshouse.gpx"},
    )

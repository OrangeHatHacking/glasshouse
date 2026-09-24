"""Dashboard routes for detection history and status."""

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from glasshouse.storage import db

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    detections = await db.get_detections(limit=50)
    history = await db.get_device_history(limit=50)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"detections": detections, "history": history},
    )


@router.get("/api/detections")
async def api_detections(limit: int = 50, offset: int = 0):
    return await db.get_detections(limit=limit, offset=offset)


@router.get("/api/history")
async def api_history(limit: int = 100):
    return await db.get_device_history(limit=limit)


@router.get("/api/status")
async def api_status():
    """Lightweight status ping for the web UI."""
    return {"status": "scanning", "version": "0.1.0"}

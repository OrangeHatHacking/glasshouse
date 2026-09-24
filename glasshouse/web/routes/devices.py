"""Device alias management routes."""

import logging
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from glasshouse.storage import db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/devices")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def devices_page(request: Request):
    history = await db.get_device_history(limit=100)
    return templates.TemplateResponse(request, "devices.html", {"history": history})


@router.post("/alias")
async def set_alias(
    mac: str = Form(...),
    alias: str = Form(...),
):
    mac = mac.strip().upper()
    alias = alias.strip()
    if not mac:
        return {"error": "MAC cannot be empty"}
    await db.set_alias(mac=mac, alias=alias)
    return RedirectResponse(url="/devices/", status_code=303)


@router.post("/clear")
async def clear_history():
    await db.clear_history()
    return RedirectResponse(url="/devices/", status_code=303)

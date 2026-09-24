"""Vendor DB view and enable/disable routes."""

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import glasshouse.vendors as vendor_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/vendors")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def vendors_page(request: Request):
    return templates.TemplateResponse(
        request,
        "vendors.html",
        {"vendors": vendor_db.VENDORS},
    )


@router.post("/toggle/{vendor_name}")
async def toggle_vendor(vendor_name: str):
    vendor = vendor_db.get_vendor_by_name(vendor_name)
    if vendor is None:
        return {"error": f"Vendor '{vendor_name}' not found"}
    for i, v in enumerate(vendor_db.VENDORS):
        if v.name.lower() == vendor_name.lower():
            vendor_db.VENDORS[i] = type(v)(**{**v.__dict__, "enabled": not v.enabled})
            break
    return RedirectResponse(url="/vendors/", status_code=303)

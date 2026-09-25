"""Vendor DB view and enable/disable routes."""

import logging
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import glasshouse.vendors as vendor_db
from glasshouse.storage import db
from glasshouse.web.auth import CSRF_TOKEN, verify_csrf

log = logging.getLogger(__name__)
router = APIRouter(prefix="/vendors")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
templates.env.globals["csrf_token"] = CSRF_TOKEN


@router.get("/", response_class=HTMLResponse)
async def vendors_page(request: Request):
    return templates.TemplateResponse(
        request,
        "vendors.html",
        {"vendors": vendor_db.get_vendor_rows()},
    )


@router.post("/toggle/{vendor_index}")
async def toggle_vendor(vendor_index: int, csrf_token: str = Form(...)):
    verify_csrf(csrf_token)
    if not 0 <= vendor_index < len(vendor_db.VENDORS):
        return {"error": "Vendor not found"}
    enabled = not vendor_db.is_vendor_enabled(vendor_index)
    vendor_db.set_vendor_enabled(vendor_index, enabled)
    await db.set_vendor_state(vendor_db.vendor_state_key(vendor_index), enabled)
    return RedirectResponse(url="/vendors/", status_code=303)


@router.post("/signature/{vendor_index}/{signature_index}")
async def toggle_signature(
    vendor_index: int, signature_index: int, csrf_token: str = Form(...)
):
    verify_csrf(csrf_token)
    if not 0 <= vendor_index < len(vendor_db.VENDORS):
        return {"error": "Vendor not found"}
    if not 0 <= signature_index < len(vendor_db.VENDORS[vendor_index].filters):
        return {"error": "Signature not found"}
    enabled = not vendor_db.is_signature_enabled(vendor_index, signature_index)
    vendor_db.set_signature_enabled(vendor_index, signature_index, enabled)
    await db.set_signature_state(
        vendor_db.signature_state_key(vendor_index, signature_index), enabled
    )
    return RedirectResponse(url="/vendors/", status_code=303)

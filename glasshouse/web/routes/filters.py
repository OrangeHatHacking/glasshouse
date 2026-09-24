"""Custom filter management routes."""

import logging
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from glasshouse.storage import db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/filters")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

VALID_TYPES = {"oui", "mac", "cid", "uuid", "name"}


@router.get("/", response_class=HTMLResponse)
async def filters_page(request: Request):
    filters = await db.get_custom_filters()
    return templates.TemplateResponse(
        request, "filters.html", {"filters": filters}
    )


@router.post("/add")
async def add_filter(
    type: str = Form(...),
    value: str = Form(...),
    description: str = Form(""),
):
    if type not in VALID_TYPES:
        return {"error": f"Invalid filter type '{type}'"}
    value = value.strip()
    if not value:
        return {"error": "Value cannot be empty"}
    await db.add_custom_filter(type_=type, value=value, description=description.strip())
    return RedirectResponse(url="/filters/", status_code=303)


@router.post("/remove/{filter_id}")
async def remove_filter(filter_id: int):
    await db.remove_custom_filter(filter_id)
    return RedirectResponse(url="/filters/", status_code=303)

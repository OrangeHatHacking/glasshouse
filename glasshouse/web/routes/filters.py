"""Custom filter management routes."""

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from glasshouse.storage import db
from glasshouse.web.auth import CSRF_TOKEN, verify_csrf

log = logging.getLogger(__name__)
router = APIRouter(prefix="/filters")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
templates.env.globals["csrf_token"] = CSRF_TOKEN

VALID_TYPES = {"oui", "mac", "cid", "uuid", "name"}


def _validate_filter(type_: str, value: str, description: str) -> tuple[str, str]:
    value = value.strip()
    description = description.strip()
    # Reject ASCII control characters below 32.
    if len(description) > 200 or any(ord(char) < 32 for char in description):
        raise ValueError("Description is invalid")
    if type_ == "oui":
        compact = re.sub(r"[:-]", "", value).replace(" ", "")
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", compact):
            raise ValueError("OUI must contain exactly 6 hexadecimal digits")
        value = ":".join(compact[index : index + 2] for index in (0, 2, 4))
    elif type_ == "mac":
        compact = re.sub(r"[:-]", "", value).replace(" ", "")
        if not re.fullmatch(r"[0-9A-Fa-f]{12}", compact):
            raise ValueError("MAC must contain exactly 12 hexadecimal digits")
        value = ":".join(compact[index : index + 2] for index in range(0, 12, 2))
    elif type_ in {"cid", "uuid"}:
        compact = value.removeprefix("0x").removeprefix("0X")
        if not re.fullmatch(r"[0-9A-Fa-f]{1,4}", compact):
            raise ValueError(f"{type_.upper()} must be a hexadecimal value")
        value = "0x" + compact.upper()
    elif type_ == "name":
        if not value or len(value) > 128 or any(ord(char) < 32 for char in value):
            raise ValueError("Name must be 1-128 printable characters")
    return value, description


@router.get("/", response_class=HTMLResponse)
async def filters_page(request: Request):
    filters = await db.get_custom_filters()
    return templates.TemplateResponse(request, "filters.html", {"filters": filters})


@router.post("/add")
async def add_filter(
    csrf_token: str = Form(...),
    type: str = Form(...),
    value: str = Form(...),
    description: str = Form(""),
):
    verify_csrf(csrf_token)
    if type not in VALID_TYPES:
        return {"error": f"Invalid filter type '{type}'"}
    try:
        value, description = _validate_filter(type, value, description)
    except ValueError as error:
        return {"error": str(error)}
    await db.add_custom_filter(type_=type, value=value, description=description.strip())
    return RedirectResponse(url="/filters/", status_code=303)


@router.post("/remove/{filter_id}")
async def remove_filter(filter_id: int, csrf_token: str = Form(...)):
    verify_csrf(csrf_token)
    await db.remove_custom_filter(filter_id)
    return RedirectResponse(url="/filters/", status_code=303)

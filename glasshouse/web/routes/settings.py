"""Routes for MQTT and hardware settings."""

import logging
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from glasshouse.storage import db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/settings")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

SETTINGS_KEYS = [
    "mqtt_enabled",
    "mqtt_broker",
    "mqtt_port",
    "mqtt_user",
    "mqtt_password",
    "mqtt_topic",
    "mqtt_tls",
    "led_enabled",
    "buzzer_enabled",
]


@router.get("/", response_class=HTMLResponse)
async def settings_page(request: Request):
    current = {}
    for key in SETTINGS_KEYS:
        current[key] = await db.get_setting(key) or ""
    # Never return the MQTT password to the template.
    if current.get("mqtt_password"):
        current["mqtt_password_set"] = True
        current["mqtt_password"] = ""
    return templates.TemplateResponse(
        request, "settings.html", {"settings": current}
    )


@router.post("/save")
async def save_settings(
    mqtt_enabled: str = Form("off"),
    mqtt_broker: str = Form(""),
    mqtt_port: str = Form("1883"),
    mqtt_user: str = Form(""),
    mqtt_password: str = Form(""),
    mqtt_topic: str = Form("glasshouse/detection"),
    mqtt_tls: str = Form("off"),
    led_enabled: str = Form("on"),
    buzzer_enabled: str = Form("off"),
):
    await db.set_setting("mqtt_enabled", "1" if mqtt_enabled == "on" else "0")
    await db.set_setting("mqtt_broker", mqtt_broker.strip())
    await db.set_setting("mqtt_port", mqtt_port.strip() or "1883")
    await db.set_setting("mqtt_user", mqtt_user.strip())
    await db.set_setting("mqtt_tls", "1" if mqtt_tls == "on" else "0")
    await db.set_setting("mqtt_topic", mqtt_topic.strip() or "glasshouse/detection")
    await db.set_setting("led_enabled", "1" if led_enabled == "on" else "0")
    await db.set_setting("buzzer_enabled", "1" if buzzer_enabled == "on" else "0")
    # Only update password if a new one was provided
    if mqtt_password.strip():
        await db.set_setting("mqtt_password", mqtt_password.strip())
    return RedirectResponse(url="/settings/", status_code=303)

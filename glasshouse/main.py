"""
Application entry point.

Starts three concurrent async tasks:
  1. BLE scanner (bleak)
  2. LED breathing loop (GPIO)
  3. FastAPI web server (uvicorn)

Registers detection callbacks for GPIO alerts and optional MQTT.
Handles graceful shutdown on SIGINT/SIGTERM.

Usage:
  Production (on Pi):   python3 -m glasshouse.main
  Development:          python3 -m glasshouse.main --debug
"""

import asyncio
import logging
import signal
import sys

import uvicorn

from glasshouse import config
from glasshouse import vendors as vendor_db
from glasshouse.alerts import gpio
from glasshouse.mqtt import client as mqtt_client
from glasshouse.scanner import ble
from glasshouse.storage import db
from glasshouse.web.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("glasshouse")
if config.DEBUG:
    log.setLevel(logging.DEBUG)

# Bleak/dbus_fast are completely quiet below WARNING in production. Their
# verbose debug output is only enabled with --debug and is written separately
# so normal console output remains usable.
for _lib_name in ("bleak", "dbus_fast"):
    _lib_logger = logging.getLogger(_lib_name)
    if not config.DEBUG:
        _lib_logger.setLevel(logging.WARNING)
        _lib_logger.propagate = True
        continue

    _ble_log_path = (
        config._dev_dir / "ble_debug.log" if hasattr(config, "_dev_dir") else None
    )
    _fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _lib_logger.setLevel(logging.DEBUG)
    _lib_logger.propagate = False

    _ch = logging.StreamHandler(sys.stdout)
    _ch.setLevel(logging.WARNING)
    _ch.setFormatter(_fmt)
    _lib_logger.addHandler(_ch)

    if _ble_log_path:
        _fh = logging.FileHandler(str(_ble_log_path), mode="a")
        _fh.setLevel(logging.DEBUG)
        _fh.setFormatter(_fmt)
        _lib_logger.addHandler(_fh)


async def main() -> None:
    if config.DEBUG:
        log.info(
            "Glasshouse starting in DEBUG mode (http://%s:%s)",
            config.AP_IP,
            config.WEB_PORT,
        )
    else:
        log.info("Glasshouse starting")

    # Initialise encrypted DB
    db.init_db()
    vendor_state, signature_state = await db.get_vendor_states()
    vendor_db.apply_saved_state(vendor_state, signature_state)
    led_enabled = await db.get_setting("led_enabled")
    gpio.set_led_enabled(led_enabled != "0")

    # Initialise GPIO (degrades gracefully if not on Pi)
    gpio.init()
    await gpio.flash_boot_ready()

    # Register detection callbacks
    ble.register_detection_callback(gpio.on_detection)
    ble.register_detection_callback(mqtt_client.on_detection)

    stop_event = asyncio.Event()

    def _handle_signal():
        log.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    app = create_app()

    uv_kwargs = {
        "app": app,
        "host": config.AP_IP,
        "port": config.WEB_PORT,
        "log_level": "debug" if config.DEBUG else "warning",
        "access_log": config.DEBUG,
    }
    if not config.DEBUG:
        uv_kwargs["ssl_certfile"] = str(config.SERVER_CERT)
        uv_kwargs["ssl_keyfile"] = str(config.SERVER_KEY)
        uv_kwargs["ssl_ca_certs"] = str(config.CA_CERT)
        uv_kwargs["ssl_cert_reqs"] = 2  # ssl.CERT_REQUIRED

    uvicorn_config = uvicorn.Config(**uv_kwargs)
    web_server = uvicorn.Server(uvicorn_config)

    async def run_web():
        await web_server.serve()

    async def run_scanner():
        await ble.run_scanner(stop_event)

    async def run_breathing():
        await gpio.breathing_loop(stop_event)

    try:
        await asyncio.gather(
            run_web(),
            run_scanner(),
            run_breathing(),
        )
    finally:
        log.info("Glasshouse shutting down")
        mqtt_client.disconnect()
        gpio.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

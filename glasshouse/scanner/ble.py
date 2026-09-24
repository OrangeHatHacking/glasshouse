"""
BLE scanner.

Uses bleak's BleakScanner in passive callback mode. Each advertisement is
passed through the match engine and fingerprint engine. Matches trigger:
  - DB insert (detection + device history update)
  - Alert (LED flash via gpio module)
  - MQTT publish (if enabled)

Cooldown tracking prevents duplicate alerts for the same device within the
vendor-defined cooldown window. Re-detections after cooldown are logged
silently with a softer alert.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from glasshouse.scanner.fingerprint import build_fingerprint, identify_by_fingerprint
from glasshouse.scanner.matcher import MatchResult, match_custom_filters, match_vendor
from glasshouse.scanner.oui_lookup import lookup_oui
from glasshouse import storage

log = logging.getLogger(__name__)

# Cooldown tracker: mac -> last detection timestamp (seconds since epoch)
_cooldowns: dict[str, float] = {}

# Callbacks registered by other modules (alerts, MQTT)
_on_detection_callbacks: list[Callable] = []

# Rolling buffer of ALL nearby BLE devices (not just matches).
# Evicted after NEARBY_TTL_SECONDS of no advertisement.
NEARBY_TTL_SECONDS = 60
_nearby_devices: dict[str, dict] = {}


def get_nearby_devices() -> list[dict]:
    """
    Return a snapshot of all currently nearby BLE devices,
    sorted by RSSI (strongest first). Auto-evicts stale entries.
    """
    now = datetime.now(timezone.utc).timestamp()
    stale = [mac for mac, d in _nearby_devices.items()
             if now - d["last_seen"] > NEARBY_TTL_SECONDS]
    for mac in stale:
        del _nearby_devices[mac]
    return sorted(_nearby_devices.values(), key=lambda d: d.get("rssi") or -999, reverse=True)


def _update_nearby(device: BLEDevice, adv: AdvertisementData) -> None:
    """Track every advertisement in the rolling buffer."""
    mac = device.address.upper()
    now = datetime.now(timezone.utc).timestamp()
    manufacturer = lookup_oui(mac)

    # Extract CIDs for display
    cids = list(adv.manufacturer_data.keys()) if adv.manufacturer_data else []

    _nearby_devices[mac] = {
        "mac": mac,
        "name": adv.local_name or "",
        "manufacturer": manufacturer,
        "rssi": adv.rssi,
        "tx_power": adv.tx_power,
        "service_uuids": [str(u) for u in (adv.service_uuids or [])],
        "company_ids": [hex(c) for c in cids],
        "last_seen": now,
    }


def register_detection_callback(fn: Callable) -> None:
    """Register an async callable to be invoked on every new detection."""
    _on_detection_callbacks.append(fn)


def _is_in_cooldown(mac: str, cooldown_seconds: int) -> bool:
    last = _cooldowns.get(mac)
    if last is None:
        return False
    elapsed = datetime.now(timezone.utc).timestamp() - last
    return elapsed < cooldown_seconds


def _update_cooldown(mac: str) -> None:
    _cooldowns[mac] = datetime.now(timezone.utc).timestamp()


def _is_redetection(mac: str) -> bool:
    """True if this MAC has been seen before (regardless of cooldown)."""
    return mac in _cooldowns


async def _handle_advertisement(
    device: BLEDevice,
    adv: AdvertisementData,
    custom_filters: list[dict],
) -> None:
    # Track ALL devices in the rolling buffer (for the /scan/ page)
    _update_nearby(device, adv)

    mac = device.address.upper()

    # Build a fingerprint for every advertisement.
    fp = build_fingerprint(
        manufacturer_data=adv.manufacturer_data or {},
        service_uuids=[str(u) for u in (adv.service_uuids or [])],
        local_name=adv.local_name,
        tx_power=adv.tx_power,
    )

    # Fingerprint-based identification (supplement to OUI/UUID matching)
    fp_hint = identify_by_fingerprint(fp)
    if fp_hint:
        log.debug("Fingerprint hint: %s for %s", fp_hint, mac)

    # Primary match: vendor DB
    result: Optional[MatchResult] = match_vendor(
        mac=mac,
        manufacturer_data=adv.manufacturer_data or {},
        service_uuids=[str(u) for u in (adv.service_uuids or [])],
        local_name=adv.local_name,
    )

    # Fallback: custom user-defined filters
    if result is None and custom_filters:
        result = match_custom_filters(
            mac=mac,
            manufacturer_data=adv.manufacturer_data or {},
            service_uuids=[str(u) for u in (adv.service_uuids or [])],
            local_name=adv.local_name,
            custom_filters=custom_filters,
        )

    if result is None:
        return

    redetection = _is_redetection(mac)

    if _is_in_cooldown(mac, result.cooldown_seconds):
        return

    _update_cooldown(mac)

    alias = await storage.db.get_alias(mac)

    log.info(
        "DETECTION | %s | vendor=%s | type=%s | rssi=%s | alias=%s | redetect=%s",
        mac,
        result.vendor,
        result.match_type,
        adv.rssi,
        alias,
        redetection,
    )

    # Persist to encrypted DB
    await storage.db.insert_detection(
        mac=mac,
        vendor=result.vendor,
        match_type=result.match_type,
        rssi=adv.rssi,
        manufacturer_data={
            str(k): v.hex() for k, v in (adv.manufacturer_data or {}).items()
        },
        service_uuids=[str(u) for u in (adv.service_uuids or [])],
        local_name=adv.local_name,
        tx_power=adv.tx_power,
        alias=alias,
    )
    await storage.db.upsert_device_history(mac=mac, alias=alias)

    # Fire registered callbacks (alerts, MQTT)
    event = {
        "mac": mac,
        "vendor": result.vendor,
        "category": result.category,
        "match_type": result.match_type,
        "matched_value": result.matched_value,
        "rssi": adv.rssi,
        "alias": alias,
        "redetection": redetection,
        "fingerprint_digest": fp.digest,
    }
    for cb in _on_detection_callbacks:
        try:
            await cb(event)
        except Exception as e:
            log.error("Detection callback error: %s", e)


async def run_scanner(stop_event: asyncio.Event) -> None:
    """
    Main scanner loop. Runs until stop_event is set.
    Reloads custom filters from DB every 60 seconds so new filters
    added via the web UI take effect without a restart.
    """
    log.info("BLE scanner starting")

    custom_filters: list[dict] = []
    last_filter_reload = 0.0

    def advertisement_callback(device: BLEDevice, adv: AdvertisementData) -> None:
        # bleak calls this synchronously from a thread. Schedule coroutine
        # on the running event loop.
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(
            asyncio.ensure_future,
            _handle_advertisement(device, adv, custom_filters),
        )

    # Try passive scanning first (lower visibility), fall back to active
    # if BlueZ doesn't support or_patterns (common on desktop Linux).
    scanner_kwargs = {"detection_callback": advertisement_callback}
    try:
        scanner = BleakScanner(scanning_mode="passive", **scanner_kwargs)
    except Exception:
        log.info("Passive scanning unavailable, using active mode")
        scanner = BleakScanner(scanning_mode="active", **scanner_kwargs)

    try:
        async with scanner:
            log.info("BLE scanner active")
            while not stop_event.is_set():
                now = asyncio.get_event_loop().time()

                # Reload custom filters periodically
                if now - last_filter_reload > 60:
                    try:
                        custom_filters = await storage.db.get_custom_filters()
                        log.debug("Custom filters reloaded: %d entries", len(custom_filters))
                    except Exception as e:
                        log.warning("Failed to reload custom filters: %s", e)
                    last_filter_reload = now

                await asyncio.sleep(1)
    except Exception as e:
        log.warning("BLE scanner failed to start: %s", e)
        log.warning("Web UI is still running - BLE scanning disabled")
        # Keep running so the web UI stays up
        while not stop_event.is_set():
            await asyncio.sleep(1)

    log.info("BLE scanner stopped")

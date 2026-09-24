"""
GPS tracker stub.

Implements the interface the rest of the codebase expects.
All functions return None/empty until a GPS dongle is connected and
the GPS module is enabled in settings.

To activate:
  1. Connect a u-blox NEO-6M/7M USB GPS dongle
  2. Install gpsd: sudo apt install gpsd gpsd-clients
  3. Configure /etc/default/gpsd to point at the correct device
  4. Install Python bindings: pip install gps3
  5. Set GPS_ENABLED=1 in /etc/glasshouse/env
  6. Implement get_current_position() using gps3.agps3 client
"""

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

GPS_ENABLED = os.environ.get("GPS_ENABLED", "0") == "1"


def is_available() -> bool:
    return GPS_ENABLED


async def get_current_position() -> Optional[dict]:
    """
    Returns the current GPS fix as:
      {"lat": float, "lon": float, "alt": float, "accuracy": float}
    or None if GPS is unavailable or no fix.
    """
    if not GPS_ENABLED:
        return None

    # TODO: implement gpsd client
    # from gps3 import agps3
    # gpsd = agps3.Gps3()
    # gpsd.connect()
    # ...
    log.debug("GPS requested but not yet implemented")
    return None


async def start_track_log(path: str) -> None:
    """Start writing a GPX track log to path."""
    if not GPS_ENABLED:
        return
    log.debug("GPS track log requested but not yet implemented")


async def add_waypoint(lat: float, lon: float, alt: float, name: str) -> None:
    """Add a named waypoint to the active track log."""
    if not GPS_ENABLED:
        return
    log.debug("GPS waypoint requested but not yet implemented")

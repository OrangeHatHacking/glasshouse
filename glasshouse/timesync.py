"""
Clock sync for offline Pi.

The Pi has no NTP, no RTC battery, and no internet. Until the phone sends
its real time, detections are stamped with a monotonic counter (seconds
since boot). On sync the math is just: real_time = mono_value + offset,
where offset = phone_epoch - current_monotonic. Only detections from
the current boot get corrected.
"""

import logging
import secrets
import subprocess
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_boot_mono = time.monotonic()
_boot_id = secrets.token_hex(4)
_synced = False

_PREFIX = "UNSYNC"


def is_synced() -> bool:
    return _synced


def boot_id() -> str:
    return _boot_id


def make_timestamp() -> str:
    """Timestamp for DB storage. ISO after sync, monotonic counter before."""
    if _synced:
        return datetime.now(timezone.utc).isoformat()
    mono = time.monotonic()
    return f"{_PREFIX}:{_boot_id}:{mono:020.6f}"


def elapsed_since(ts: str) -> float | None:
    """Seconds since a pre-sync timestamp, or None if it's a real timestamp."""
    parsed = _parse_unsync(ts)
    if parsed is None:
        return None
    _, mono = parsed
    return time.monotonic() - mono


def format_elapsed(seconds: float) -> str:
    """Human-readable relative time string."""
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m {s % 60}s ago"
    return f"{s // 3600}h {(s % 3600) // 60}m ago"


def is_unsync_ts(ts: str) -> bool:
    return ts.startswith(f"{_PREFIX}:")


def _parse_unsync(ts: str) -> tuple[str, float] | None:
    if not ts.startswith(f"{_PREFIX}:"):
        return None
    parts = ts.split(":", 2)
    if len(parts) != 3:
        return None
    try:
        return parts[1], float(parts[2])
    except ValueError:
        return None


def _set_system_clock(epoch: float) -> bool:
    try:
        subprocess.run(
            ["date", "-u", "-s", f"@{epoch}"],
            check=True,
            capture_output=True,
            timeout=5,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        log.error("Failed to set system clock: %s", exc)
        return False


async def sync_from_client(epoch: float) -> dict:
    global _synced
    from glasshouse.storage import db

    mono_now = time.monotonic()
    offset = epoch - mono_now
    old_time = time.time()

    count = await db.fix_unsync_detections(_boot_id, offset)

    ok = _set_system_clock(epoch)
    if not ok:
        return {"synced": False, "error": "failed to set system clock"}

    _synced = True
    drift = epoch - old_time

    log.info(
        "Clock synced: drift=%.1fs, corrected %d detections",
        drift, count,
    )

    return {
        "synced": True,
        "old_time": int(old_time),
        "new_time": int(epoch),
        "drift": round(drift, 1),
        "corrected": count,
    }

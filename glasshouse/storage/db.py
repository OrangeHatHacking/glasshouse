"""
SQLCipher-encrypted SQLite database layer.

The encryption key is derived from a secret stored at /etc/glasshouse/secret
(root:root, 0600). The key is never written to disk in plaintext beyond that
file. All database access is only done through this module.

Tables:
  detections    - every BLE match event
  filters       - user-defined custom filters (vendor DB is hardcoded)
  settings      - key/value config store
"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from glasshouse import config

log = logging.getLogger(__name__)

SECRET_PATH = config.SECRET_PATH
DB_PATH = config.DB_PATH


def _load_key() -> str:
    """
    Read the encryption key from the secret file.
    Raises RuntimeError if the file is missing or unreadable.
    """
    try:
        key = SECRET_PATH.read_text().strip()
    except FileNotFoundError:
        raise RuntimeError(
            f"Glasshouse secret not found at {SECRET_PATH}. "
            "Run setup/firstboot.py first."
        )
    except PermissionError:
        raise RuntimeError(f"Cannot read {SECRET_PATH}. Is this running as root?")
    if not key:
        raise RuntimeError(f"Secret file at {SECRET_PATH} is empty.")
    return key


def _get_connection() -> sqlite3.Connection:
    """
    Open a SQLCipher-encrypted connection.

    sqlcipher3 exposes the same interface as sqlite3 but requires the PRAGMA
    key to be set immediately after opening, before any other operation.
    """
    try:
        import sqlcipher3
    except ImportError:
        raise RuntimeError(
            "sqlcipher3 is required and not installed. "
            "Install the system library first (libsqlcipher-dev on Debian, "
            "sqlcipher on Arch), then: pip install sqlcipher3"
        )
    conn = sqlcipher3.connect(str(DB_PATH))

    key = _load_key()
    # Key must be set before any other PRAGMA or query.
    conn.execute(f"PRAGMA key = '{key}'")
    conn.execute("PRAGMA cipher_page_size = 4096")
    conn.execute("PRAGMA kdf_iter = 64000")
    conn.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512")
    conn.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512")
    conn.row_factory = sqlcipher3.Row
    return conn


def init_db() -> None:
    """
    Create tables if they don't exist. Safe to call on every startup.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS detections (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp         TEXT    NOT NULL,
                mac               TEXT    NOT NULL,
                vendor            TEXT,
                match_type        TEXT,
                rssi              INTEGER,
                manufacturer_data TEXT,
                service_uuids     TEXT,
                local_name        TEXT,
                tx_power          INTEGER,
                lat               REAL,
                lon               REAL,
                alt               REAL
            );

            CREATE INDEX IF NOT EXISTS idx_detections_mac
                ON detections (mac);
            CREATE INDEX IF NOT EXISTS idx_detections_timestamp
                ON detections (timestamp);

            CREATE TABLE IF NOT EXISTS filters (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                type        TEXT    NOT NULL,
                value       TEXT    NOT NULL,
                description TEXT,
                enabled     INTEGER NOT NULL DEFAULT 1
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_filters_type_value
                ON filters (type, value);

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(detections)").fetchall()
        }
        if "alias" in columns:
            conn.execute("ALTER TABLE detections DROP COLUMN alias")
        conn.execute("DROP TABLE IF EXISTS device_history")
        conn.commit()
        log.info("Database initialised at %s", DB_PATH)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Async wrappers. Blocking SQLite calls run in a thread pool so they don't
# block the asyncio event loop.
# ---------------------------------------------------------------------------


async def _run(fn, *args) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, *args)


def _insert_detection_sync(row: dict) -> int:
    conn = _get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO detections
                (timestamp, mac, vendor, match_type, rssi,
                 manufacturer_data, service_uuids, local_name, tx_power,
                 lat, lon, alt)
            VALUES
                (:timestamp, :mac, :vendor, :match_type, :rssi,
                 :manufacturer_data, :service_uuids, :local_name, :tx_power,
                 :lat, :lon, :alt)
            """,
            row,
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


async def insert_detection(
    mac: str,
    vendor: str | None,
    match_type: str,
    rssi: int | None,
    manufacturer_data: dict | None,
    service_uuids: list[str] | None,
    local_name: str | None,
    tx_power: int | None,
    lat: float | None = None,
    lon: float | None = None,
    alt: float | None = None,
) -> int:
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mac": mac.upper(),
        "vendor": vendor,
        "match_type": match_type,
        "rssi": rssi,
        "manufacturer_data": json.dumps(manufacturer_data)
        if manufacturer_data
        else None,
        "service_uuids": json.dumps(service_uuids) if service_uuids else None,
        "local_name": local_name,
        "tx_power": tx_power,
        "lat": lat,
        "lon": lon,
        "alt": alt,
    }
    return await _run(_insert_detection_sync, row)


def _get_detections_sync(
    limit: int, offset: int, since: str | None = None
) -> list[dict]:
    conn = _get_connection()
    try:
        if since:
            rows = conn.execute(
                """
                SELECT * FROM detections
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (since, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM detections
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def get_detections(
    limit: int = 100, offset: int = 0, since: str | None = None
) -> list[dict]:
    return await _run(_get_detections_sync, limit, offset, since)


def _get_latest_detections_sync(
    limit: int, since: str | None = None, sort_by: str = "last_seen"
) -> list[dict]:
    conn = _get_connection()
    try:
        sort_column = "first_seen" if sort_by == "first_seen" else "last_seen"
        where = "WHERE timestamp >= ?" if since else ""
        params = (since, limit) if since else (limit,)
        rows = conn.execute(
            f"""
            SELECT * FROM (
                SELECT detections.*,
                       MIN(timestamp) OVER (PARTITION BY mac) AS first_seen,
                       MAX(timestamp) OVER (PARTITION BY mac) AS last_seen,
                       ROW_NUMBER() OVER (
                           PARTITION BY mac
                           ORDER BY timestamp DESC, id DESC
                       ) AS row_number
                FROM detections
                {where}
            )
            WHERE row_number = 1
            ORDER BY {sort_column} DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def get_latest_detections(
    limit: int = 100, since: str | None = None, sort_by: str = "last_seen"
) -> list[dict]:
    return await _run(_get_latest_detections_sync, limit, since, sort_by)


def _get_filters_sync() -> list[dict]:
    conn = _get_connection()
    try:
        rows = conn.execute("SELECT * FROM filters WHERE enabled = 1").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def get_custom_filters() -> list[dict]:
    """Return user-defined filters from DB (not the hardcoded vendor DB)."""
    return await _run(_get_filters_sync)


def _add_filter_sync(type_: str, value: str, description: str) -> int:
    conn = _get_connection()
    try:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO filters (type, value, description)
            VALUES (?, ?, ?)
            """,
            (type_, value.upper(), description),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


async def add_custom_filter(type_: str, value: str, description: str = "") -> int:
    return await _run(_add_filter_sync, type_, value, description)


def _remove_filter_sync(filter_id: int) -> None:
    conn = _get_connection()
    try:
        conn.execute("DELETE FROM filters WHERE id = ?", (filter_id,))
        conn.commit()
    finally:
        conn.close()


async def remove_custom_filter(filter_id: int) -> None:
    await _run(_remove_filter_sync, filter_id)


def _get_setting_sync(key: str) -> str | None:
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


async def get_setting(key: str) -> str | None:
    return await _run(_get_setting_sync, key)


def _set_setting_sync(key: str, value: str) -> None:
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


async def set_setting(key: str, value: str) -> None:
    await _run(_set_setting_sync, key, value)


def _get_vendor_states_sync() -> tuple[dict[str, bool], dict[str, bool]]:
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE 'vendor.%'"
        ).fetchall()
        vendors: dict[str, bool] = {}
        signatures: dict[str, bool] = {}
        for row in rows:
            key = row["key"]
            if key.startswith("vendor.enabled."):
                vendor_key = key.removeprefix("vendor.enabled.")
                if vendor_key.isdigit():
                    vendor_key = f"#{vendor_key}"
                vendors[vendor_key] = row["value"] == "1"
            elif key.startswith("vendor.signature.enabled."):
                signature_key = key.removeprefix("vendor.signature.enabled.")
                parts = signature_key.split(":")
                if len(parts) == 2 and all(part.isdigit() for part in parts):
                    signature_key = f"#{parts[0]}:{parts[1]}"
                signatures[signature_key] = row["value"] == "1"
        return vendors, signatures
    finally:
        conn.close()


async def get_vendor_states() -> tuple[dict[str, bool], dict[str, bool]]:
    return await _run(_get_vendor_states_sync)


async def set_vendor_state(vendor_key: str, enabled: bool) -> None:
    await set_setting(f"vendor.enabled.{vendor_key}", "1" if enabled else "0")


async def set_signature_state(signature_key: str, enabled: bool) -> None:
    await set_setting(
        f"vendor.signature.enabled.{signature_key}",
        "1" if enabled else "0",
    )


def _clear_history_sync() -> None:
    conn = _get_connection()
    try:
        conn.execute("DELETE FROM detections")
        conn.commit()
    finally:
        conn.close()


async def clear_history() -> None:
    await _run(_clear_history_sync)

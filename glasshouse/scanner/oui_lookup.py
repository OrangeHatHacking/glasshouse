"""
Bundled OUI lookup. No network access required.

Loads the full IEEE MA-L OUI registry (~40k entries) from a compressed file
bundled with the application (oui.txt.gz, ~409 KB). Decompresses into memory
on first use (~1.3 MB dict). No network calls at runtime.

The oui.txt.gz file is generated from the IEEE CSV at:
  https://standards-oui.ieee.org/oui/oui.csv

Format of oui.txt (inside the gzip): one entry per line, "AABBCC:Company Name"
"""

import gzip
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_OUI_DB: dict[str, str] | None = None
_OUI_FILE = Path(__file__).parent / "oui.txt.gz"


def _load_db() -> dict[str, str]:
    """Load and decompress the OUI database on first access."""
    global _OUI_DB
    if _OUI_DB is not None:
        return _OUI_DB

    db = {}
    try:
        with gzip.open(_OUI_FILE, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if ":" not in line:
                    continue
                # Format: AABBCC:Company Name
                # Split on first colon only (company names can contain colons)
                oui_hex, _, name = line.partition(":")
                if oui_hex and name:
                    # Convert AABBCC to AA:BB:CC for lookup
                    oui_hex = oui_hex.upper()
                    if len(oui_hex) == 6:
                        key = f"{oui_hex[0:2]}:{oui_hex[2:4]}:{oui_hex[4:6]}"
                        db[key] = name
        log.info("OUI database loaded: %d entries", len(db))
    except FileNotFoundError:
        log.warning("OUI database not found at %s - lookups will return Unknown", _OUI_FILE)
    except Exception as e:
        log.warning("Failed to load OUI database: %s", e)

    _OUI_DB = db
    return _OUI_DB


def is_randomised_mac(mac: str) -> bool:
    """
    Check if a MAC address is locally-administered (randomised).
    The second nibble of the first byte indicates this:
    bit 1 of byte 0 is the U/L bit. If set, the address is locally
    administered (i.e. randomised, not assigned by IEEE).
    In hex: second character is 2, 3, 6, 7, A, B, E, or F.
    """
    mac = mac.upper().replace("-", ":").replace(".", ":").strip()
    if len(mac) < 2:
        return False
    first_byte_str = mac.replace(":", "")[:2]
    try:
        first_byte = int(first_byte_str, 16)
    except ValueError:
        return False
    return bool(first_byte & 0x02)


def lookup_oui(mac: str) -> str:
    """
    Look up the manufacturer for a MAC address.
    Returns the company name, "Randomised" for locally-administered MACs,
    or "Unknown" if not in the local database.
    """
    if is_randomised_mac(mac):
        return "Randomised"
    parts = mac.upper().replace("-", ":").replace(".", ":").split(":")
    if len(parts) < 3:
        return "Unknown"
    prefix = ":".join(parts[:3])
    return _load_db().get(prefix, "Unknown")

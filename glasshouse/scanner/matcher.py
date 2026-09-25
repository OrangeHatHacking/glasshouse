"""
Match engine.

Takes a parsed BLE advertisement and tests it against the hardcoded vendor DB
plus any user-defined custom filters from the DB.

Returns a MatchResult if any filter fires, None otherwise.

Match priority (first match wins per vendor):
  1. composite  - most specific, checked first to avoid false positives
  2. oui        - fast prefix check
  3. cid        - manufacturer data company ID
  4. uuid       - service UUID
  5. name       - local name substring
"""

import logging
from dataclasses import dataclass

from glasshouse import vendors as vendor_db
from glasshouse.vendors import (
    VENDORS,
    CIDFilter,
    CompositeFilter,
    NameFilter,
    OUIFilter,
    UUIDFilter,
)

log = logging.getLogger(__name__)


@dataclass
class MatchResult:
    vendor: str
    category: str
    match_type: str  # 'oui' | 'cid' | 'uuid' | 'name' | 'composite' | 'custom'
    matched_value: str  # human-readable description of what fired
    cooldown_seconds: int


def _normalise_oui(mac: str) -> str:
    """Extract and uppercase the first 3 bytes from a MAC address."""
    parts = mac.upper().replace("-", ":").split(":")
    return ":".join(parts[:3])


def _parse_cids(manufacturer_data: dict[int, bytes]) -> set[int]:
    """
    bleak provides manufacturer_data as {company_id: bytes}.
    Return the set of company IDs present.
    """
    return set(manufacturer_data.keys())


def _parse_service_uuids(service_uuids: list[str]) -> set[int]:
    """
    Convert bleak's UUID strings to a set of 16-bit ints.
    bleak returns short UUIDs as '0000xxxx-0000-1000-8000-00805f9b34fb'.
    We only care about the 16-bit segment.
    """
    result = set()
    for uuid_str in service_uuids:
        uuid_str = uuid_str.lower().strip()
        # Short form: '0000fc81-0000-1000-8000-00805f9b34fb'
        if uuid_str.startswith("0000") and len(uuid_str) == 36:
            try:
                result.add(int(uuid_str[4:8], 16))
            except ValueError:
                pass
        # Already a short hex string like 'fc81'
        elif len(uuid_str) == 4:
            try:
                result.add(int(uuid_str, 16))
            except ValueError:
                pass
    return result


def _match_composite(
    f: CompositeFilter,
    cids: set[int],
    uuids: set[int],
    local_name: str | None,
) -> bool:
    """
    Composite match: CID AND UUID must both be present (if specified),
    OR any of the name substrings match.
    """
    name_lower = local_name.lower() if local_name else ""

    # A name match is sufficient on its own.
    if f.names:
        for n in f.names:
            if n.lower() in name_lower:
                return True

    # Both CID and UUID must be present for this path.
    cid_ok = (f.cid is None) or (f.cid in cids)
    uuid_ok = (f.uuid is None) or (f.uuid in uuids)
    return cid_ok and uuid_ok and (f.cid is not None or f.uuid is not None)


def match_vendor(
    mac: str,
    manufacturer_data: dict[int, bytes],
    service_uuids: list[str],
    local_name: str | None,
) -> MatchResult | None:
    """
    Test a BLE advertisement against all enabled vendor filters.
    Returns the first MatchResult, or None.
    """
    oui = _normalise_oui(mac)
    cids = _parse_cids(manufacturer_data)
    uuids = _parse_service_uuids(service_uuids)

    for vendor_index, vendor in enumerate(VENDORS):
        if not vendor_db.is_vendor_enabled(vendor_index):
            continue

        # Sort filters: composite first, then oui, cid, uuid, name
        ordered = sorted(
            enumerate(vendor.filters),
            key=lambda item: {
                "composite": 0,
                "oui": 1,
                "cid": 2,
                "uuid": 3,
                "name": 4,
            }.get(item[1].type, 9),
        )

        for signature_index, f in ordered:
            if not vendor_db.is_signature_enabled(vendor_index, signature_index):
                continue
            if isinstance(f, CompositeFilter):
                if _match_composite(f, cids, uuids, local_name):
                    return MatchResult(
                        vendor=vendor.name,
                        category=vendor.category,
                        match_type="composite",
                        matched_value=f"CID={hex(f.cid) if f.cid else 'any'} "
                        f"UUID={hex(f.uuid) if f.uuid else 'any'} "
                        f"names={f.names}",
                        cooldown_seconds=vendor.alert_cooldown_seconds,
                    )

            elif isinstance(f, OUIFilter):
                if oui == f.oui:
                    return MatchResult(
                        vendor=vendor.name,
                        category=vendor.category,
                        match_type="oui",
                        matched_value=f.oui,
                        cooldown_seconds=vendor.alert_cooldown_seconds,
                    )

            elif isinstance(f, CIDFilter):
                if f.cid in cids:
                    return MatchResult(
                        vendor=vendor.name,
                        category=vendor.category,
                        match_type="cid",
                        matched_value=hex(f.cid),
                        cooldown_seconds=vendor.alert_cooldown_seconds,
                    )

            elif isinstance(f, UUIDFilter):
                if f.uuid in uuids:
                    return MatchResult(
                        vendor=vendor.name,
                        category=vendor.category,
                        match_type="uuid",
                        matched_value=hex(f.uuid),
                        cooldown_seconds=vendor.alert_cooldown_seconds,
                    )

            elif (
                isinstance(f, NameFilter)
                and local_name
                and f.substring.lower() in local_name.lower()
            ):
                return MatchResult(
                    vendor=vendor.name,
                    category=vendor.category,
                    match_type="name",
                    matched_value=f.substring,
                    cooldown_seconds=vendor.alert_cooldown_seconds,
                )

    return None


def match_custom_filters(
    mac: str,
    manufacturer_data: dict[int, bytes],
    service_uuids: list[str],
    local_name: str | None,
    custom_filters: list[dict],
) -> MatchResult | None:
    """
    Test against user-defined filters from the DB.
    Each filter is a dict: {type, value, description}.
    """
    oui = _normalise_oui(mac)
    cids = _parse_cids(manufacturer_data)
    uuids = _parse_service_uuids(service_uuids)

    for f in custom_filters:
        ftype = f.get("type", "")
        value = f.get("value", "").upper()
        desc = f.get("description", value)

        if ftype == "oui" and oui == value:
            return MatchResult(
                vendor=desc,
                category="custom",
                match_type="custom:oui",
                matched_value=value,
                cooldown_seconds=30,
            )

        elif ftype == "mac" and mac.upper() == value:
            return MatchResult(
                vendor=desc,
                category="custom",
                match_type="custom:mac",
                matched_value=value,
                cooldown_seconds=30,
            )

        elif ftype == "cid":
            try:
                cid_int = int(value, 16)
                if cid_int in cids:
                    return MatchResult(
                        vendor=desc,
                        category="custom",
                        match_type="custom:cid",
                        matched_value=value,
                        cooldown_seconds=30,
                    )
            except ValueError:
                log.warning("Invalid CID filter value: %s", value)

        elif ftype == "uuid":
            try:
                uuid_int = int(value, 16)
                if uuid_int in uuids:
                    return MatchResult(
                        vendor=desc,
                        category="custom",
                        match_type="custom:uuid",
                        matched_value=value,
                        cooldown_seconds=30,
                    )
            except ValueError:
                log.warning("Invalid UUID filter value: %s", value)

        elif ftype == "name" and local_name and value.lower() in local_name.lower():
            return MatchResult(
                vendor=desc,
                category="custom",
                match_type="custom:name",
                matched_value=value,
                cooldown_seconds=30,
            )

    return None

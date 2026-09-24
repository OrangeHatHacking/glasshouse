"""
Payload fingerprint engine.

Used to strengthen or disambiguate matches when MAC addresses are randomised.
Builds a fingerprint from advertisement invariants that don't change when the
MAC rotates: manufacturer data structure, service UUID set, TX power, and
advertisement interval (where measurable).

This is a best-effort layer. Fingerprinting can't guarantee identity, only
increase or decrease confidence in a match. Results are logged alongside the
primary match but do not override it.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class Fingerprint:
    """
    Stable advertisement fingerprint derived from payload invariants.
    Two advertisements with the same fingerprint likely come from the
    same device class, possibly the same device instance.
    """
    digest: str                         # SHA-256 of stable fields
    cid_set: frozenset[int]             # company IDs seen
    uuid_set: frozenset[int]            # 16-bit service UUIDs seen
    tx_power: Optional[int]             # advertised TX power (dBm)
    has_manufacturer_data: bool
    manufacturer_data_lengths: tuple[int, ...]  # payload byte lengths per CID
    local_name: Optional[str]


def build_fingerprint(
    manufacturer_data: dict[int, bytes],
    service_uuids: list[str],
    local_name: Optional[str],
    tx_power: Optional[int],
) -> Fingerprint:
    """
    Build a stable fingerprint from advertisement payload.
    The MAC address is intentionally excluded because we want invariants.
    """
    # Normalise CIDs
    cid_set = frozenset(manufacturer_data.keys())

    # Normalise service UUIDs to 16-bit ints where possible
    uuid_set: set[int] = set()
    for uuid_str in service_uuids:
        uuid_str = uuid_str.lower().strip()
        if uuid_str.startswith("0000") and len(uuid_str) == 36:
            try:
                uuid_set.add(int(uuid_str[4:8], 16))
            except ValueError:
                pass
        elif len(uuid_str) == 4:
            try:
                uuid_set.add(int(uuid_str, 16))
            except ValueError:
                pass

    # Manufacturer data payload lengths (sorted by CID for determinism)
    mfr_lengths = tuple(
        len(v) for _, v in sorted(manufacturer_data.items())
    )

    # Build digest from stable fields
    h = hashlib.sha256()
    h.update(repr(sorted(cid_set)).encode())
    h.update(repr(sorted(uuid_set)).encode())
    h.update(repr(mfr_lengths).encode())
    if tx_power is not None:
        h.update(str(tx_power).encode())
    if local_name:
        h.update(local_name.lower().encode())

    return Fingerprint(
        digest=h.hexdigest(),
        cid_set=cid_set,
        uuid_set=frozenset(uuid_set),
        tx_power=tx_power,
        has_manufacturer_data=bool(manufacturer_data),
        manufacturer_data_lengths=mfr_lengths,
        local_name=local_name,
    )


def fingerprints_similar(a: Fingerprint, b: Fingerprint) -> bool:
    """
    Heuristic similarity check between two fingerprints.
    Used to correlate a new randomised MAC with a previously seen device.

    Returns True if the fingerprints are likely from the same device/class.
    Full digest equality is sufficient but not required. Partial matches
    on CID+UUID set are enough to flag similarity.
    """
    if a.digest == b.digest:
        return True

    # Same CID and UUID sets.
    if a.cid_set and a.cid_set == b.cid_set and a.uuid_set == b.uuid_set:
        return True

    # Same UUID set and TX power.
    if (
        a.uuid_set
        and a.uuid_set == b.uuid_set
        and a.tx_power is not None
        and a.tx_power == b.tx_power
    ):
        return True

    return False


# ---------------------------------------------------------------------------
# Known payload patterns for specific devices.
# These augment OUI/CID/UUID matching when MACs are fully randomised.
# Extend this dict as new captures become available.
# ---------------------------------------------------------------------------

# Format: 'description' -> callable(Fingerprint) -> bool
KNOWN_PATTERNS: dict[str, callable] = {

    # Sepura SC21: BLE used for companion app pairing.
    # Pattern TBD. Add manufacturer data structure once captures are available.
    # Placeholder always returns False until real data is added.
    "Sepura SC21 (placeholder)": lambda fp: False,

    # Axon body cameras advertise CID 0x034D (TASER) reliably.
    "Axon bodycam (CID 0x034D)": lambda fp: 0x034D in fp.cid_set,

    # Meta Ray-Ban: Luxottica CID (0x0D53) + Meta UUID (0xFD5F)
    "Meta Ray-Ban glasses": lambda fp: (
        0x0D53 in fp.cid_set and 0xFD5F in fp.uuid_set
    ),

}


def identify_by_fingerprint(fp: Fingerprint) -> Optional[str]:
    """
    Check a fingerprint against known device patterns.
    Returns the pattern description if matched, None otherwise.
    """
    for description, check in KNOWN_PATTERNS.items():
        try:
            if check(fp):
                return description
        except Exception as e:
            log.debug("Pattern check error for '%s': %s", description, e)
    return None

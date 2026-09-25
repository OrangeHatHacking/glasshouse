"""
Hardcoded vendor database.

Each vendor entry defines one or more filter signatures. The matcher engine
processes these in order. All OUIs are stored as uppercase, colon-separated
3-byte prefixes. CIDs and UUIDs are stored as integers for fast comparison.

Filter types:
  oui       - match first 3 bytes of MAC (works even with randomised MACs
              when the manufacturer hasn't enabled full randomisation)
  cid       - match BT SIG company ID in manufacturer data
  uuid      - match 16-bit service UUID in advertisement
  name      - case-insensitive substring match on local name
  composite - ALL sub-conditions must match (AND logic) in one advertisement
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OUIFilter:
    type: str = "oui"
    oui: str = ""  # e.g. "00:1E:96"


@dataclass(frozen=True)
class CIDFilter:
    type: str = "cid"
    cid: int = 0  # BT SIG company ID as int, e.g. 0x034D


@dataclass(frozen=True)
class UUIDFilter:
    type: str = "uuid"
    uuid: int = 0  # 16-bit service UUID as int, e.g. 0xFC81


@dataclass(frozen=True)
class NameFilter:
    type: str = "name"
    substring: str = ""  # case-insensitive


@dataclass(frozen=True)
class CompositeFilter:
    """All conditions must be present in the same advertisement."""

    type: str = "composite"
    cid: int | None = None
    uuid: int | None = None
    names: tuple[str, ...] = field(
        default_factory=tuple
    )  # any one name match sufficient


@dataclass
class Vendor:
    name: str
    category: str  # 'bodycam' | 'drone' | 'doorbell' | 'radio' | 'smartglass'
    description: str
    filters: list
    alert_cooldown_seconds: int = 30
    enabled: bool = True


VENDORS: list[Vendor] = [
    # -------------------------------------------------------------------------
    # Ring / Amazon
    # Source: IEEE OUI registry, Ring LLC registrations
    # Note: Amazon Technologies has hundreds of OUIs across all products.
    #       Only Ring LLC dedicated registrations are included here to avoid
    #       false positives from Kindle, Echo, and other Amazon hardware.
    # -------------------------------------------------------------------------
    Vendor(
        name="Ring",
        category="doorbell",
        description="Ring video doorbells and security cameras (Amazon)",
        alert_cooldown_seconds=30,
        filters=[
            OUIFilter(oui="00:B4:63"),
            OUIFilter(oui="18:7F:88"),
            OUIFilter(oui="24:2B:D6"),
            OUIFilter(oui="34:3E:A4"),
            OUIFilter(oui="50:E4:67"),
            OUIFilter(oui="54:E0:19"),
            OUIFilter(oui="5C:47:5E"),
            OUIFilter(oui="64:9A:63"),
            OUIFilter(oui="90:48:6C"),
            OUIFilter(oui="9C:76:13"),
            OUIFilter(oui="AC:9F:C3"),
            OUIFilter(oui="C4:DB:AD"),
            OUIFilter(oui="CC:3B:FB"),
        ],
    ),
    # -------------------------------------------------------------------------
    # DJI
    # Source: IEEE OUI registry
    # Subsidiaries: Sz Dji Technology, DJI Osmo Technology, Dji Baiwang,
    #               SZ DJI Ronin Technology
    # -------------------------------------------------------------------------
    Vendor(
        name="DJI",
        category="drone",
        description="DJI consumer and professional drones, gimbals",
        alert_cooldown_seconds=15,
        filters=[
            OUIFilter(oui="04:A8:5A"),
            OUIFilter(oui="0C:9A:E6"),
            OUIFilter(oui="20:1F:55"),
            OUIFilter(oui="34:D2:62"),
            OUIFilter(oui="48:1C:B9"),
            OUIFilter(oui="4C:43:F6"),
            OUIFilter(oui="58:B8:58"),
            OUIFilter(oui="60:60:1F"),
            OUIFilter(oui="8C:58:23"),
            OUIFilter(oui="9C:5A:8A"),
            OUIFilter(oui="34:D2:70"),
            OUIFilter(oui="EC:72:F7"),
            OUIFilter(oui="E4:7A:2C"),
            OUIFilter(oui="F8:40:68"),
        ],
    ),
    # -------------------------------------------------------------------------
    # Axon Enterprise (formerly TASER International)
    # Body cameras: Axon Body 2, 3, 4; Fleet dash cams
    # Source: IEEE OUI registry + BT SIG assigned numbers
    #   OUI:  00:25:DF - Axon Enterprise, Inc.
    #   CID:  0x034D  - TASER International (BT SIG company ID)
    #   UUID: 0xFC81  - Axon proprietary BLE service
    #
    # OUI matching is the weakest signal. Axon cameras may not expose their OUI
    # in BLE advertisements. CID and UUID do most of the work.
    # Composite match fires on CID + UUID together to reduce false positives.
    # -------------------------------------------------------------------------
    Vendor(
        name="Axon",
        category="bodycam",
        description="Axon body cameras and TASER devices",
        alert_cooldown_seconds=30,
        filters=[
            OUIFilter(oui="00:25:DF"),
            CIDFilter(cid=0x034D),
            UUIDFilter(uuid=0xFC81),
            CompositeFilter(cid=0x034D, uuid=0xFC81),
        ],
    ),
    # -------------------------------------------------------------------------
    # Meta / Ray-Ban smart glasses
    # Ray-Ban Stories, Ray-Ban Meta (Wayfarer, Oakley Meta)
    #
    # These use Resolvable Private Addresses (RPA). The MAC rotates per BT spec.
    # OUI matching is pure noise for these devices. Do not add OUI filters.
    #
    # Source: BT SIG assigned numbers
    #   CID:  0x0D53 - Luxottica Group S.p.A. (manufacturer)
    #   UUID: 0xFD5F - Meta Platforms (service UUID)
    #
    # Composite logic: CID 0x0D53 AND UUID 0xFD5F in same advertisement,
    # OR local name contains any of the known product name substrings.
    #
    # WARNING: UUID 0xFD5F alone causes false positives. Phones running
    # Meta apps also advertise it. CID must be present too.
    # -------------------------------------------------------------------------
    Vendor(
        name="Meta / Ray-Ban",
        category="smartglass",
        description="Meta Ray-Ban smart glasses (Stories, Wayfarer, Oakley Meta)",
        alert_cooldown_seconds=30,
        filters=[
            CompositeFilter(
                cid=0x0D53,
                uuid=0xFD5F,
                names=("Ray-Ban", "Wayfarer", "Oakley Meta"),
            ),
        ],
    ),
    # -------------------------------------------------------------------------
    # Sepura TETRA radios
    # SC21, SC2020, STP9000 series - used by police and emergency services
    # Source: IEEE OUI registry
    #   OUI: 00:1E:96 - Sepura plc
    #
    # Modern Sepura radios may have BLE for companion app pairing.
    # OUI is the primary detection method. Manufacturer data pattern matching
    # can be added here once advertisement captures are available.
    # -------------------------------------------------------------------------
    Vendor(
        name="Sepura",
        category="radio",
        description="Sepura TETRA digital radios (SC21, SC2020, STP9000 series)",
        alert_cooldown_seconds=60,
        filters=[
            OUIFilter(oui="00:1E:96"),
            # TODO: add CIDFilter and manufacturer data pattern once BLE
            # advertisement captures from SC21 hardware are available.
        ],
    ),
    # -------------------------------------------------------------------------
    # Motorola Solutions
    # TETRA/P25/DMR radios, MOTOTRBO series, APX series
    # Source: IEEE OUI registry
    #   OUI: 00:04:7D - Motorola Solutions (legacy)
    #   OUI: 00:0A:28 - Motorola Solutions
    #
    # Low confidence. Many Motorola products share these OUIs and modern
    # handsets may use contract manufacturer MACs. BLE may also be disabled in
    # operational use. Treat this as weak evidence.
    # -------------------------------------------------------------------------
    Vendor(
        name="Motorola Solutions",
        category="radio",
        description="Motorola Solutions digital radios (MOTOTRBO, APX, TETRA)",
        alert_cooldown_seconds=60,
        filters=[
            OUIFilter(oui="00:04:7D"),
            OUIFilter(oui="00:0A:28"),
        ],
    ),
]

_vendor_enabled: dict[str, bool] = {}
_signature_enabled: dict[str, bool] = {}


def signature_label(signature: object) -> str:
    if isinstance(signature, OUIFilter):
        return f"OUI {signature.oui}"
    if isinstance(signature, CIDFilter):
        return f"Company ID {hex(signature.cid)}"
    if isinstance(signature, UUIDFilter):
        return f"Service UUID {hex(signature.uuid)}"
    if isinstance(signature, NameFilter):
        return f"Name contains {signature.substring}"
    if isinstance(signature, CompositeFilter):
        parts = []
        if signature.cid is not None:
            parts.append(f"CID {hex(signature.cid)}")
        if signature.uuid is not None:
            parts.append(f"UUID {hex(signature.uuid)}")
        if signature.names:
            parts.append("name: " + ", ".join(signature.names))
        return " + ".join(parts)
    return str(signature)


def vendor_state_key(vendor_index: int) -> str:
    return VENDORS[vendor_index].name


def signature_state_key(vendor_index: int, signature_index: int) -> str:
    return f"{VENDORS[vendor_index].name}|{signature_label(VENDORS[vendor_index].filters[signature_index])}"


def is_vendor_enabled(vendor_index: int) -> bool:
    return _vendor_enabled.get(
        vendor_state_key(vendor_index), VENDORS[vendor_index].enabled
    )


def is_signature_enabled(vendor_index: int, signature_index: int) -> bool:
    return _signature_enabled.get(
        signature_state_key(vendor_index, signature_index), True
    )


def set_vendor_enabled(vendor_index: int, enabled: bool) -> None:
    _vendor_enabled[vendor_state_key(vendor_index)] = enabled
    VENDORS[vendor_index].enabled = enabled


def set_signature_enabled(
    vendor_index: int, signature_index: int, enabled: bool
) -> None:
    _signature_enabled[signature_state_key(vendor_index, signature_index)] = enabled


def apply_saved_state(
    vendor_state: dict[str, bool], signature_state: dict[str, bool]
) -> None:
    for vendor_index, vendor in enumerate(VENDORS):
        legacy_vendor_key = f"#{vendor_index}"
        if vendor.name in vendor_state:
            set_vendor_enabled(vendor_index, vendor_state[vendor.name])
        elif legacy_vendor_key in vendor_state:
            set_vendor_enabled(vendor_index, vendor_state[legacy_vendor_key])
        for signature_index in range(len(vendor.filters)):
            key = signature_state_key(vendor_index, signature_index)
            legacy_key = f"#{vendor_index}:{signature_index}"
            if key in signature_state:
                set_signature_enabled(
                    vendor_index, signature_index, signature_state[key]
                )
            elif legacy_key in signature_state:
                set_signature_enabled(
                    vendor_index, signature_index, signature_state[legacy_key]
                )


def get_vendor_rows() -> list[dict]:
    return [
        {
            "index": vendor_index,
            "vendor": vendor,
            "enabled": is_vendor_enabled(vendor_index),
            "signatures": [
                {
                    "index": signature_index,
                    "label": signature_label(signature),
                    "enabled": is_signature_enabled(vendor_index, signature_index),
                }
                for signature_index, signature in enumerate(vendor.filters)
            ],
        }
        for vendor_index, vendor in enumerate(VENDORS)
    ]


def has_enabled_oui(mac: str) -> bool:
    parts = mac.upper().replace("-", ":").split(":")
    if len(parts) < 3:
        return False
    oui = ":".join(parts[:3])
    for vendor_index, vendor in enumerate(VENDORS):
        if not is_vendor_enabled(vendor_index):
            continue
        for signature_index, signature in enumerate(vendor.filters):
            if (
                isinstance(signature, OUIFilter)
                and signature.oui == oui
                and is_signature_enabled(vendor_index, signature_index)
            ):
                return True
    return False


def get_enabled_vendors() -> list[Vendor]:
    """Return only vendors that are currently enabled."""
    return [v for v in VENDORS if v.enabled]


def get_vendor_by_name(name: str) -> Vendor | None:
    """Case-insensitive vendor lookup."""
    name_lower = name.lower()
    return next((v for v in VENDORS if v.name.lower() == name_lower), None)

# Glasshouse

Passive BLE surveillance-hardware detector for Raspberry Pi Zero 2W with a view to being adaptable depending on how many peripherals are available (rpi3+ with wifi antenna or sdr attachments).

Detects known surveillance devices by OUI prefix (now known as MAC-L available from IEEE database),
BLE manufacturer data, service UUIDs, and composite payload
fingerprinting. Alerts via LED. Logs to AES-256 encrypted SQLite. 
Managed via a hidden WPA3 access point with mutual-TLS secured web console accessible from Android or GrapheneOS.

## Hardware

- Raspberry Pi Zero 2W (in reality any linux system with bluetooth capabilities)
- LED + resistor on GPIO 17
- Buzzer on GPIO 18 (optional)
- Any USB power bank

## Quick start

```bash
git clone https://github.com/yourusername/glasshouse
cd glasshouse
sudo python3 setup/firstboot.py
```

First boot:
- Generates mTLS certificates (CA + server + client)
- Generates random WPA3 AP password
- Configures hostapd, dnsmasq, nftables
- Enables glasshouse systemd service
- Prints AP credentials and cert import instructions

## Connecting from Android / GrapheneOS

1. Transfer `glasshouse-client.p12` from `/home/pi/` to your phone
2. Settings -> Security -> Encryption & credentials -> Install certificate -> VPN & app user certificate
3. Connect to the Glasshouse AP (SSID printed on first boot)
4. Open `https://192.168.4.1` in browser
5. Select the installed certificate when prompted

## Detected vendors

| Vendor | Method |
|--------|--------|
| Ring / Amazon | OUI prefix |
| DJI | OUI prefix |
| Axon bodycams | OUI + manufacturer CID + service UUID |
| Meta / Ray-Ban | Composite: CID + UUID + device name |
| Sepura TETRA radios | OUI + manufacturer data |

Additional vendors and custom OUI/UUID filters can be added via the web UI.

## Adding new vendors

Web UI → Filters → Add filter. Supports:
- OUI prefix (`AA:BB:CC`)
- Full MAC (`AA:BB:CC:DD:EE:FF`)
- BT SIG company ID (`0x034D`)
- Service UUID (`0xFC81`)
- Device name substring
- Composite (multiple conditions, AND logic)

## Future expansion

### GPS logging (stubs in place)

DB schema has `lat/lon/alt` columns, `gps/tracker.py` has the interface stubbed.

**Equipment:** u-blox NEO-6M or NEO-7M USB GPS dongle. Plug into USB OTG.

**Software:** `gpsd` + `gps3` Python bindings.

Adds detection events tagged with coordinates. GPX export for mapping
where detections occurred over time.

### TETRA radio detection (requires SDR)

BLE cannot detect TETRA radios when they're transmitting on the TETRA network
(380-400 MHz). Sepura OUI matching only works if the radio's BLE is active for
companion app pairing, which is often disabled in operational use.

To detect TETRA radio presence reliably, you need an SDR (Software Defined Radio)
receiver monitoring the TETRA downlink band.

**Equipment:**

| Item | Cost | Notes |
|------|------|-------|
| RTL-SDR v3/v4 USB dongle | Covers 24-1766 MHz, includes TETRA band |
| 380-400 MHz antenna | Quarter-wave whip or small Yagi for better range |
| USB OTG hub | Pi Zero 2W only has one USB port (shared with GPS if used) |

**Frequencies (Ireland / EU TETRA allocation):**

| Band | Range | Usage |
|------|-------|-------|
| Uplink | 380-385 MHz | Handset → base station |
| Downlink | 390-395 MHz | Base station → handset |
| Direct mode | 380-400 MHz | Handset → handset (no base station) |

**What you can detect:**
- Presence of TETRA transmissions within SDR range (~50-200m depending on
  antenna and environment)
- Whether a TETRA radio is actively transmitting (keyed up)
- Control channel beacons from TETRA base stations

**What you cannot detect/decode:**
- Voice or data content (it's encrypted with TEA2 in Ireland and most of the EU)
- Individual handset identity (encrypted at the air interface)
- Which specific handset is transmitting

**Certainty level: presence detection only.** You can say "a TETRA radio is
transmitting nearby" but you cannot identify who, which unit, or what's being
said. This is analogous to hearing a radio crackle without understanding the
language.

**Implementation approach:**
- Run `rtl_fm` or `rtl_power` as a separate process monitoring 380-400 MHz
- Feed power-level readings into Glasshouse's detection engine
- Alert when sustained signal energy is detected in the TETRA band
- Log signal strength over time for pattern analysis
- Software: `pyrtlsdr` or subprocess calls to `rtl_power`
- Pi Zero 2W CPU is sufficient for power-level monitoring (not full decoding)

**Power impact:** RTL-SDR dongle draws ~300mA. With a 10,000mAh power bank,
expect ~2-3 days runtime (vs 4-5 days BLE-only).

### WiFi probe request capture (requires USB adapter)

The Pi Zero 2W's built-in WiFi chip (BCM43438) does not support monitor mode,
which is required to passively capture WiFi probe requests from nearby devices.

**Equipment:**

| Item | Notes |
|------|-------|
| USB WiFi adapter with monitor mode support | Alfa AWUS036ACH or TP-Link TL-WN722N v1 (must be v1 with Atheros chipset) |
| USB OTG hub | Needed if also using GPS or SDR |

**What it adds:**
- Detect devices probing for known WiFi networks (reveals device presence even
  when not connected)
- MAC address capture from probe requests (most modern devices randomise though)
- SSID history from probe requests (reveals networks the device has connected to)
- Can complement BLE scanning because some devices disable BLE but still probe for WiFi

**Certainty level: moderate.** Modern iOS and Android randomise MAC addresses in
probe requests, reducing identification accuracy. However, some devices
(especially older ones) still
use their real MAC in probes.

**Implementation approach:**
- Put the USB adapter into monitor mode (`airmon-ng` or `iw`)
- Capture with `scapy` or `tshark` filtering for probe request frames
- Feed captured MACs into the same matcher engine used for BLE
- Built-in WiFi remains on the AP for the web UI (separate interface)

### Buzzer (stub in place)

GPIO 18 is configured for PWM output. Wire a passive buzzer between GPIO 18
and GND. Set `buzzer_enabled` to true in web UI settings.

## Security

- WPA3-Personal hidden AP
- Mutual TLS on web console (no cert = TCP connection dropped, no 403)
- SQLCipher AES-256 encrypted database
- All secrets in `/etc/glasshouse/` (root:root, 600)
- nftables firewall: only port 443 reachable on AP interface
- No internet connection, no telemetry, no cloud

## License

GPL-3.0

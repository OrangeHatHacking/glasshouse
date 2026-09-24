#!/usr/bin/env python3
"""
First boot setup for Glasshouse.

Generates:
  - mTLS CA, server cert, and client cert (P12 for Android import)
  - Random WPA3 AP credentials
  - /etc/glasshouse/secret (DB encryption key)

Must be run as root. Safe to re-run.
"""

import os
import secrets
import stat
import string
import subprocess
import sys
from pathlib import Path

# Require root
if os.geteuid() != 0:
    print("ERROR: firstboot.py must be run as root (sudo python3 setup/firstboot.py)")
    sys.exit(1)

CONF_DIR = Path("/etc/glasshouse")
CERT_DIR = CONF_DIR / "certs"
VAR_DIR = Path("/var/lib/glasshouse")
SECRET_FILE = CONF_DIR / "secret"
AP_CONF = CONF_DIR / "ap.conf"
CLIENT_P12 = Path("/home/pi/glasshouse-client.p12")

# Try to find the home dir of the non-root user who invoked sudo
_sudo_user = os.environ.get("SUDO_USER", "pi")
_user_home = Path(f"/home/{_sudo_user}")
if _user_home.exists():
    CLIENT_P12 = _user_home / "glasshouse-client.p12"


def _secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chown(path, 0, 0)
    path.chmod(0o700)


def _write_secret(path: Path, content: str) -> None:
    path.write_text(content)
    os.chown(path, 0, 0)
    path.chmod(0o600)


def _random_password(length: int = 32) -> str:
    # Alphanumeric strong enough (32 chars =~ 190 bits of entropy)
    # Symbols would introduce possible parser bugs
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _random_hex(length: int = 32) -> str:
    return secrets.token_hex(length)


def step_directories() -> None:
    print("[1/5] Creating directories...")
    _secure_dir(CONF_DIR)
    _secure_dir(CERT_DIR)
    _secure_dir(VAR_DIR)
    os.chown(VAR_DIR, 0, 0)
    VAR_DIR.chmod(0o700)
    print("      Done.")


def step_db_secret() -> None:
    print("[2/5] Generating database encryption key...")
    if SECRET_FILE.exists():
        print("      Already exists - skipping.")
        return
    key = _random_hex(32)
    _write_secret(SECRET_FILE, key)
    print("      Written to", SECRET_FILE)


def step_certs() -> None:
    print("[3/5] Generating mTLS certificates...")
    ca_key = CERT_DIR / "ca.key"
    ca_crt = CERT_DIR / "ca.crt"
    srv_key = CERT_DIR / "server.key"
    srv_csr = CERT_DIR / "server.csr"
    srv_crt = CERT_DIR / "server.crt"
    cli_key = CERT_DIR / "client.key"
    cli_csr = CERT_DIR / "client.csr"
    cli_crt = CERT_DIR / "client.crt"

    if ca_crt.exists() and srv_crt.exists() and cli_crt.exists():
        print("      Certificates already exist - skipping.")
        _export_p12(cli_key, cli_crt, ca_crt)
        return

    def run(*args):
        subprocess.run(args, check=True, capture_output=True)

    # CA
    run("openssl", "genrsa", "-out", str(ca_key), "4096")
    run("openssl", "req", "-new", "-x509", "-days", "3650",
        "-key", str(ca_key), "-out", str(ca_crt),
        "-subj", "/CN=Glasshouse-CA/O=Glasshouse")

    # Server cert
    run("openssl", "genrsa", "-out", str(srv_key), "4096")
    run("openssl", "req", "-new", "-key", str(srv_key), "-out", str(srv_csr),
        "-subj", "/CN=192.168.4.1/O=Glasshouse")
    run("openssl", "x509", "-req", "-days", "3650",
        "-in", str(srv_csr), "-CA", str(ca_crt), "-CAkey", str(ca_key),
        "-CAcreateserial", "-out", str(srv_crt))

    # Client cert
    run("openssl", "genrsa", "-out", str(cli_key), "4096")
    run("openssl", "req", "-new", "-key", str(cli_key), "-out", str(cli_csr),
        "-subj", "/CN=glasshouse-client/O=Glasshouse")
    run("openssl", "x509", "-req", "-days", "3650",
        "-in", str(cli_csr), "-CA", str(ca_crt), "-CAkey", str(ca_key),
        "-CAcreateserial", "-out", str(cli_crt))

    # Secure permissions
    for key_file in [ca_key, srv_key, cli_key]:
        os.chown(f, 0, 0)
        key_file.chmod(0o600)
    for crt_file in [ca_crt, srv_crt, cli_crt]:
        os.chown(f, 0, 0)
        crt_file.chmod(0o644)

    _export_p12(cli_key, cli_crt, ca_crt)
    print("      Certificates written to", CERT_DIR)


def _export_p12(cli_key: Path, cli_crt: Path, ca_crt: Path) -> None:
    """Export client cert as PKCS#12 for Android import (no password on P12)."""
    subprocess.run([
        "openssl", "pkcs12", "-export",
        "-inkey", str(cli_key),
        "-in", str(cli_crt),
        "-certfile", str(ca_crt),
        "-out", str(CLIENT_P12),
        "-passout", "pass:",
        "-name", "Glasshouse",
    ], check=True, capture_output=True)
    # Make readable by the non-root user
    try:
        import pwd
        uid = pwd.getpwnam(_sudo_user).pw_uid
        os.chown(CLIENT_P12, uid, -1)
    except Exception:
        pass
    CLIENT_P12.chmod(0o644)
    print(f"      Client cert exported to {CLIENT_P12}")


def step_ap_credentials() -> None:
    print("[4/5] Generating AP credentials...")
    if AP_CONF.exists():
        print("      Already exists - skipping.")
        # Still print the SSID for reference
        content = AP_CONF.read_text()
        for line in content.splitlines():
            if line.startswith("SSID=") or line.startswith("PASSWORD="):
                print("     ", line)
        return

    ssid = f"gl-{secrets.token_hex(4)}"
    password = _random_password(32)

    conf = f"SSID={ssid}\nPASSWORD={password}\n"
    _write_secret(AP_CONF, conf)

    # Write hostapd config
    hostapd_conf = Path("/etc/hostapd/hostapd.conf")
    hostapd_tmpl = Path(__file__).parent / "hostapd.conf.tmpl"
    if hostapd_tmpl.exists():
        tmpl = hostapd_tmpl.read_text()
        tmpl = tmpl.replace("{{SSID}}", ssid).replace("{{PASSWORD}}", password)
        hostapd_conf.write_text(tmpl)
        hostapd_conf.chmod(0o600)

    print(f"      SSID:     {ssid}")
    print(f"      Password: {password}")
    print("      (Also saved to /etc/glasshouse/ap.conf)")


def step_services() -> None:
    print("[5/5] Enabling services...")
    services = ["hostapd", "dnsmasq", "glasshouse"]
    for svc in services:
        result = subprocess.run(
            ["systemctl", "enable", svc],
            capture_output=True,
        )
        status = "OK" if result.returncode == 0 else "SKIP (not installed yet)"
        print(f"      {svc}: {status}")


def main() -> None:
    print("=" * 50)
    print("  GLASSHOUSE FIRST BOOT SETUP")
    print("=" * 50)
    step_directories()
    step_db_secret()
    step_certs()
    step_ap_credentials()
    step_services()
    print()
    print("=" * 50)
    print("  SETUP COMPLETE")
    print("=" * 50)
    print()
    print("AP credentials are in /etc/glasshouse/ap.conf (root only)")
    print()


if __name__ == "__main__":
    main()

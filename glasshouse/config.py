"""Runtime configuration."""

import argparse
import os
import secrets
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Glasshouse BLE detector")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Debug mode: bind to 127.0.0.1:8080, no TLS, no mTLS, "
        "auto-create local dev secret and DB in ./dev_data/",
    )
    parser.add_argument("--host", help="Debug bind address")
    parser.add_argument("--port", type=int, help="Debug web port")
    return parser.parse_args()


_args = parse_args()
DEBUG = _args.debug

if DEBUG:
    _dev_dir = Path(__file__).parent.parent / "dev_data"
    _dev_dir.mkdir(exist_ok=True)

    # Auto-create a dev secret if it doesn't exist
    _dev_secret = _dev_dir / "secret"
    if not _dev_secret.exists():
        _dev_secret.write_text(secrets.token_hex(32))

    AP_IP = _args.host or "127.0.0.1"
    WEB_PORT = _args.port or 8080
    SECRET_PATH = _dev_secret
    CERT_DIR = _dev_dir / "certs"
    DB_PATH = _dev_dir / "glasshouse.db"
    SERVER_CERT = None
    SERVER_KEY = None
    CA_CERT = None
else:
    AP_IP = "192.168.4.1"
    WEB_PORT = 443
    SECRET_PATH = Path("/etc/glasshouse/secret")
    CERT_DIR = Path("/etc/glasshouse/certs")
    DB_PATH = Path("/var/lib/glasshouse/glasshouse.db")
    SERVER_CERT = CERT_DIR / "server.crt"
    SERVER_KEY = CERT_DIR / "server.key"
    CA_CERT = CERT_DIR / "ca.crt"

AP_INTERFACE = os.environ.get("GLASSHOUSE_AP_IFACE", "wlan0")

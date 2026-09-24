#!/usr/bin/env bash
# Glasshouse install script for Raspberry Pi Zero 2W (Raspberry Pi OS / Debian)
# Run as root: sudo bash setup/install.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: Run as root: sudo bash setup/install.sh"
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "===================================="
echo "  GLASSHOUSE INSTALL"
echo "===================================="
echo "Repo: $REPO_DIR"
echo

# 1. System packages
echo "[1/6] Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends \
  python3 python3-pip python3-venv \
  hostapd dnsmasq nftables \
  libsqlcipher-dev \
  openssl \
  bluez bluez-tools \
  git
echo "      Done."

# 2. Python virtual environment
echo "[2/6] Setting up Python virtualenv..."
python3 -m venv /opt/glasshouse/venv
/opt/glasshouse/venv/bin/pip install --upgrade pip -q
/opt/glasshouse/venv/bin/pip install -r "$REPO_DIR/requirements.txt" -q
echo "      Done."

# 3. Copy application
echo "[3/6] Installing application..."
cp -r "$REPO_DIR/glasshouse" /opt/glasshouse/
echo "      Done."

# 4. Network config
echo "[4/6] Configuring network..."
# Disable wpa_supplicant on wlan0 (we're running our own AP)
systemctl disable wpa_supplicant 2>/dev/null || true
# Copy dnsmasq config
cp "$REPO_DIR/setup/dnsmasq.conf" /etc/dnsmasq.d/glasshouse.conf
# Install the static-IP fragment for wlan0.
install -d -m 0755 /etc/dhcpcd.conf.d
install -m 0644 "$REPO_DIR/setup/dhcpcd.conf" \
  /etc/dhcpcd.conf.d/glasshouse.conf
echo "      Done."

# 5. nftables firewall
echo "[5/6] Installing firewall rules..."
cp "$REPO_DIR/setup/nftables.conf" /etc/nftables.conf
systemctl enable nftables
systemctl restart nftables
echo "      Done."

# 6. systemd service
echo "[6/6] Installing systemd service..."
cp "$REPO_DIR/systemd/glasshouse.service" /etc/systemd/system/glasshouse.service

systemctl daemon-reload
systemctl enable glasshouse
echo "      Done."

echo
echo "===================================="
echo "  INSTALL COMPLETE"
echo "===================================="
echo
echo "Now run: sudo python3 $REPO_DIR/setup/firstboot.py"
echo

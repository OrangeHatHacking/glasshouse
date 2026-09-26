#!/usr/bin/env bash
# Glasshouse install script for Raspberry Pi Zero 2W (Raspberry Pi OS / Debian)
# Run as root: sudo bash setup/install.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: Run as root: sudo bash setup/install.sh"
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  echo "Usage: sudo bash setup/install.sh [--user USER]"
}

detect_operator_user() {
  if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]] && id "$SUDO_USER" &>/dev/null; then
    echo "$SUDO_USER"
    return
  fi

  if id pi &>/dev/null; then
    echo pi
    return
  fi

  getent passwd | awk -F: '$3 >= 1000 && $7 !~ /(nologin|false)$/ { print $1; exit }'
}

OPERATOR_USER="$(detect_operator_user)"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      OPERATOR_USER="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ ! "$OPERATOR_USER" =~ ^[a-z_][a-z0-9_-]*\$?$ ]] || ! id "$OPERATOR_USER" &>/dev/null; then
  echo "ERROR: operator user '$OPERATOR_USER' does not exist"
  exit 1
fi

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
  openssh-server \
  curl \
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
cp "$REPO_DIR/setup/start-ap.sh" /opt/glasshouse/start-ap.sh
cp "$REPO_DIR/setup/hostapd-wpa2.conf.tmpl" /opt/glasshouse/hostapd-wpa2.conf.tmpl
chmod 0755 /opt/glasshouse/start-ap.sh
echo "      Done."

# 4. Network config
echo "[4/6] Configuring network..."
# Disable wpa_supplicant on wlan0 (we're running our own AP)
systemctl disable wpa_supplicant 2>/dev/null || true
# Copy dnsmasq config
cp "$REPO_DIR/setup/dnsmasq.conf" /etc/dnsmasq.d/glasshouse.conf
# Install SSH configuration
install -d -m 0755 /etc/ssh/sshd_config.d
sed "s/{{SSH_USER}}/$OPERATOR_USER/" \
  "$REPO_DIR/setup/sshd_config.d/glasshouse.conf" \
  > /etc/ssh/sshd_config.d/glasshouse.conf
chmod 0644 /etc/ssh/sshd_config.d/glasshouse.conf
sshd -t
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
echo "[6/7] Installing systemd service..."
cp "$REPO_DIR/systemd/glasshouse.service" /etc/systemd/system/glasshouse.service
cp "$REPO_DIR/systemd/glasshouse-ap.service" /etc/systemd/system/glasshouse-ap.service

systemctl disable hostapd 2>/dev/null || true

systemctl daemon-reload
systemctl enable ssh
systemctl enable glasshouse-ap
systemctl enable glasshouse
echo "[7/7] Applying host hardening..."
bash "$REPO_DIR/setup/harden.sh"
echo "      Done."

echo
echo "===================================="
echo "  INSTALL COMPLETE"
echo "===================================="
echo

if [[ -t 0 ]]; then
  read -r -p "Run first-boot setup now? [Y/n] " RUN_FIRSTBOOT || RUN_FIRSTBOOT="n"
  if [[ -z "$RUN_FIRSTBOOT" || "$RUN_FIRSTBOOT" =~ ^[Yy]$ ]]; then
    python3 "$REPO_DIR/setup/firstboot.py" --user "$OPERATOR_USER"
    echo
    echo "Copy the client certificate from another terminal:"
    echo "  scp ${OPERATOR_USER}@glasshouse.local:glasshouse-client.p12 ."
    echo
    read -r -p "Press Enter after copying the certificate to start the private AP..." _ || true
    systemctl restart dnsmasq glasshouse-ap glasshouse
    echo "Private AP started."
  else
    echo "Run first-boot setup later with:"
    echo "  sudo python3 $REPO_DIR/setup/firstboot.py --user $OPERATOR_USER"
  fi
else
  echo "Run first-boot setup later with:"
  echo "  sudo python3 $REPO_DIR/setup/firstboot.py --user $OPERATOR_USER"
fi
echo

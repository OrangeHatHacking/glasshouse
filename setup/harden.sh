#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: harden.sh must run as root"
  exit 1
fi

# Disable serial login consoles. Leave UART routing alone because Bluetooth
# uses an internal UART on these boards.
for service in \
  serial-getty@serial0.service \
  serial-getty@ttyAMA0.service \
  serial-getty@ttyS0.service; do
  systemctl disable --now "$service" 2>/dev/null || true
done

# Remove serial console output from the kernel command line.
for cmdline in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
  if [[ -f "$cmdline" ]]; then
    sed -E -i \
      's/ ?console=(serial[0-9]+|ttyAMA[0-9]+|ttyS[0-9]+),[0-9]+//g' \
      "$cmdline"
  fi
done

# Keep application data and configuration private.
install -d -o root -g root -m 0700 /etc/glasshouse /var/lib/glasshouse
if [[ -d /etc/glasshouse/certs ]]; then
  chmod 0700 /etc/glasshouse/certs
  find /etc/glasshouse/certs -type f -name '*.key' -exec chmod 0600 {} +
  find /etc/glasshouse/certs -type f -name '*.crt' -exec chmod 0644 {} +
fi
if [[ -f /etc/glasshouse/secret ]]; then
  chmod 0600 /etc/glasshouse/secret
fi
if [[ -f /etc/glasshouse/ap.conf ]]; then
  chmod 0600 /etc/glasshouse/ap.conf
fi

systemctl daemon-reload

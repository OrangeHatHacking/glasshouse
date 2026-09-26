#!/usr/bin/env bash
set -u

WPA2_TEMPLATE=/opt/glasshouse/hostapd-wpa2.conf.tmpl
HOSTAPD_CONFIG=/etc/hostapd/hostapd.conf

systemctl start hostapd
if systemctl is-active --quiet hostapd; then
  exit 0
fi

logger -t glasshouse "WPA3 AP failed; falling back to WPA2-Personal"

ssid="$(sed -n 's/^SSID=//p' /etc/glasshouse/ap.conf)"
password="$(sed -n 's/^PASSWORD=//p' /etc/glasshouse/ap.conf)"
sed "s/{{SSID}}/$ssid/; s/{{PASSWORD}}/$password/" \
  "$WPA2_TEMPLATE" > "$HOSTAPD_CONFIG"

systemctl reset-failed hostapd 2>/dev/null || true
systemctl restart hostapd
if ! systemctl is-active --quiet hostapd; then
  logger -t glasshouse "WPA2 AP also failed to start"
  exit 1
fi

logger -t glasshouse "WPA2-Personal AP started after WPA3 fallback"

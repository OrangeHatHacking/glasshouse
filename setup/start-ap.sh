#!/usr/bin/env bash
set -u

WPA2_TEMPLATE=/opt/glasshouse/hostapd-wpa2.conf.tmpl
HOSTAPD_CONFIG=/etc/hostapd/hostapd.conf
AP_INTERFACE=${GLASSHOUSE_AP_IFACE:-wlan0}

if ! ip link show "$AP_INTERFACE" >/dev/null 2>&1; then
  logger -t glasshouse "AP interface not found: $AP_INTERFACE"
  exit 1
fi

if command -v nmcli >/dev/null 2>&1; then
  nmcli device set "$AP_INTERFACE" managed no || true
fi
ip link set "$AP_INTERFACE" up
ip addr flush dev "$AP_INTERFACE"
ip addr add 192.168.4.1/24 dev "$AP_INTERFACE"

systemctl unmask hostapd
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

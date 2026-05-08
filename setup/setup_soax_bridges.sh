#!/bin/bash
# setup_soax_bridges.sh — start local SOCKS5 bridges (gost) per-geo for SOAX residential.
#
# Why: chromium does not support SOCKS5 with auth. We strip auth via local gost
# listeners (one per geo), and chromium connects to localhost:port (no auth).
#
# After running this script, the bridges listen on ports defined in BRIDGES below.
# Set ANTIBLOCK_BRIDGE_PORTS env var to the same mapping so anti_block tools find them:
#
#     export ANTIBLOCK_BRIDGE_PORTS="IN:11080,BR:11082,DE:11085,GB:11088"
#
# Configuration via env:
#   SOAX_RES_PASSWORD — your SOAX residential password (required)
#   SOAX_RES_PACKAGE  — your SOAX package id (required, find in soax.com dashboard)
#   SOAX_RES_HOST     — SOAX endpoint host (default: proxy.soax.com)
#   SOAX_RES_PORT     — SOAX endpoint port (default: 5000)
#   GOST_BIN          — path to gost binary (default: /usr/local/bin/gost)
#   LOG_DIR           — log directory (default: /var/log)
#
# Bridges to start (edit BRIDGES array below). Each line: "geo_code:local_port:sessionid_seed".
#
# Requirements: gost (https://github.com/ginuerzh/gost) installed.

set -euo pipefail

: "${SOAX_RES_PASSWORD:?SOAX_RES_PASSWORD env var required}"
: "${SOAX_RES_PACKAGE:?SOAX_RES_PACKAGE env var required (find in soax.com dashboard)}"
SOAX_HOST="${SOAX_RES_HOST:-proxy.soax.com}"
SOAX_PORT="${SOAX_RES_PORT:-5000}"
GOST_BIN="${GOST_BIN:-/usr/local/bin/gost}"
LOG_DIR="${LOG_DIR:-/var/log}"

if [ ! -x "$GOST_BIN" ]; then
    echo "ERROR: gost binary not found at $GOST_BIN" >&2
    echo "Install: https://github.com/ginuerzh/gost/releases" >&2
    exit 1
fi

# Edit this array to define your bridges.
# Format: "GEO:LOCAL_PORT:SESSIONID_SEED"
# Sessionid_seed must be 8-16 alphanumeric chars (no hyphens — SOAX rejects).
BRIDGES=(
    "IN:11080:abIN1234"
    "BR:11082:abBR1234"
    "MX:11083:abMX1234"
    "CI:11084:abCI1234"
    "DE:11085:abDE1234"
    "PL:11086:abPL1234"
    "RS:11087:abRS1234"
    "GB:11088:abGB1234"
    "FR:11089:abFR1234"
    "CA:11090:abCA1234"
)

start_bridge() {
    local geo=$1
    local port=$2
    local sid=$3
    local username="package-${SOAX_RES_PACKAGE}-country-${geo,,}-sessionid-${sid}-sessionlength-300"

    pkill -f "gost -L=socks5://:${port}" 2>/dev/null || true
    sleep 0.3
    nohup "$GOST_BIN" -L="socks5://:${port}" \
        -F="socks5://${username}:${SOAX_RES_PASSWORD}@${SOAX_HOST}:${SOAX_PORT}" \
        >> "${LOG_DIR}/soax-bridge-${geo}.log" 2>&1 &
    echo "[$(date -u +%H:%M:%S)] Bridge ${geo} on :${port} started PID=$!"
}

echo "Starting ${#BRIDGES[@]} SOAX bridges..."
for spec in "${BRIDGES[@]}"; do
    IFS=':' read -r geo port sid <<< "$spec"
    start_bridge "$geo" "$port" "$sid"
done

sleep 1
echo
echo "Listening ports:"
ss -tlnp 2>/dev/null | grep -oE ':[0-9]+' | sort -u | grep -E ':1108[0-9]|:11090' | head

echo
echo "Set this env var so anti_block tools find the bridges:"
echo
echo -n "export ANTIBLOCK_BRIDGE_PORTS=\""
first=1
for spec in "${BRIDGES[@]}"; do
    IFS=':' read -r geo port sid <<< "$spec"
    if [ $first -eq 1 ]; then first=0; else echo -n ","; fi
    echo -n "$geo:$port"
done
echo "\""

echo
echo "To run on systemd boot, copy this script to /usr/local/bin/ and create a systemd unit:"
echo "    /etc/systemd/system/soax-bridges.service"
echo "    ExecStart=/usr/local/bin/setup_soax_bridges.sh"
echo "    Type=forking"

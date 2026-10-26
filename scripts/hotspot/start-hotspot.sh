#!/usr/bin/env bash
#***********************************************************************
# Start the MuSoHu hotspot with a fixed gateway address.
# Description: Use NetworkManager shared mode for Wi-Fi, DHCP and DNS.
# Usage: sudo bash start-hotspot.sh [--help]
# Example: sudo bash scripts/hotspot/start-hotspot.sh
# Prerequisites: NetworkManager, wlP1p1s0 and network-management privileges.
# Author: MuSoHu Team
# Date: 2026-10-21
#***********************************************************************
set -euo pipefail
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            cat <<'HELP'
Usage: sudo bash start-hotspot.sh [--help]
Activate the saved Hotspot profile on wlP1p1s0, replacing its current Wi-Fi
connection. Create the profile if absent (SSID Robotixx_MuSoHu).
The gateway is 10.42.0.1/24; NetworkManager supplies DHCP and DNS.
Open http://10.42.0.1:8000 after connecting your phone to the hotspot.
Existing hotspot credentials are preserved. No internet is needed for the UI
or phone time sync. LiDAR eno1 and ROS localhost settings are unchanged.
Stop/return to Wi-Fi: sudo bash scripts/hotspot/stop-hotspot.sh --ssid <profile>
HELP
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
hotspot_start_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$hotspot_start_dir/../utils/logging_config.sh"
trap 'log_error "Hotspot startup failed at line $LINENO"' ERR
command -v nmcli >/dev/null || { log_error 'NetworkManager is required.'; exit 1; }
if ! nmcli connection show Hotspot >/dev/null 2>&1; then
    log_info 'Creating the MuSoHu hotspot profile.'
    nmcli connection add type wifi ifname wlP1p1s0 con-name Hotspot \
        ssid Robotixx_MuSoHu 802-11-wireless.mode ap \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk Robotixx \
        connection.autoconnect no ipv4.method shared ipv4.addresses 10.42.0.1/24
fi
[[ $(nmcli -g 802-11-wireless.mode connection show Hotspot) == ap ]] || {
    log_error 'The saved Hotspot profile is not an access point; refusing to activate it.'; exit 1;
}
nmcli connection modify Hotspot connection.interface-name wlP1p1s0 \
    ipv4.method shared ipv4.addresses 10.42.0.1/24
log_info 'Activating hotspot; the current Wi-Fi connection will disconnect.'
nmcli connection up Hotspot
log_success 'Hotspot ready. Open http://10.42.0.1:8000 for MuSoHu.'

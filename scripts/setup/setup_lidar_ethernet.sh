#!/usr/bin/env bash

#***********************************************************************
# Configure helmet Ethernet for the RoboSense LiDAR
#***********************************************************************
# Reuse the helmet's LiDAR profile and its observed host IP address.
# Usage: sudo bash scripts/setup/setup_lidar_ethernet.sh [--help]
#***********************************************************************

set -euo pipefail

#***********************************************************************
# Help and argument parsing
#***********************************************************************

show_help() {
    cat <<'EOF'
Usage: sudo bash scripts/setup/setup_lidar_ethernet.sh [OPTIONS]

Configure eno1 using the LiDAR profile with host address 192.168.1.102/24.
No gateway or DNS is configured; this connection cannot become a default route.
IPv6 stays automatic, matching the helmet's existing LiDAR configuration.
Disable autoconnect for "Wired connection 1" and activate LiDAR immediately.
Existing profiles are updated; missing profiles are created.

Options:
  -h, --help  Show this help message

Requires root, NetworkManager (nmcli), iproute2, and an eno1 interface.
Switching modes interrupts traffic on eno1. Run over WiFi or locally.
Logs: scripts/logs/

Example:
  sudo bash scripts/setup/setup_lidar_ethernet.sh
Restore DHCP with: sudo bash scripts/setup/reset_ethernet.sh
EOF
}

if [[ $# -gt 0 ]]; then
    case "$1" in
        -h|--help) show_help; exit 0 ;;
        *) echo "Unknown argument: $1 (use --help)" >&2; exit 1 ;;
    esac
fi

#***********************************************************************
# Configuration and prerequisites
#***********************************************************************

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../utils/logging_config.sh"

IFACE="eno1"
CON_NAME="LiDAR"
DHCP_CON_NAME="Wired connection 1"
IPV4_ADDR="192.168.1.102/24"

if [[ "$EUID" -ne 0 ]]; then
    log_error "Run with sudo: sudo bash scripts/setup/setup_lidar_ethernet.sh"
    exit 1
fi
for required_command in nmcli ip; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        log_error "Required command not found: $required_command"
        exit 1
    fi
done
ip link show dev "$IFACE" >/dev/null
nmcli connection show >/dev/null

#***********************************************************************
# Configure and activate the LiDAR profile
#***********************************************************************

if ! nmcli connection show id "$CON_NAME" >/dev/null 2>&1; then
    nmcli connection add type ethernet ifname "$IFACE" con-name "$CON_NAME" \
        connection.autoconnect no ipv4.method manual ipv4.addresses "$IPV4_ADDR"
fi

log_info "Configuring $CON_NAME on $IFACE with $IPV4_ADDR"
nmcli connection modify id "$CON_NAME" \
    connection.interface-name "$IFACE" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    ipv4.method manual \
    ipv4.addresses "$IPV4_ADDR" \
    ipv4.gateway "" ipv4.routes "" ipv4.dns "" ipv4.dns-search "" \
    ipv4.never-default yes \
    ipv6.method auto ipv6.never-default yes

if nmcli connection show id "$DHCP_CON_NAME" >/dev/null 2>&1; then
    nmcli connection modify id "$DHCP_CON_NAME" connection.autoconnect no
fi

if ! nmcli --wait 30 connection up id "$CON_NAME" ifname "$IFACE"; then
    log_error "LiDAR profile saved, but activation failed. Check the Ethernet cable and retry."
    exit 1
fi
log_success "Connection $CON_NAME is up on $IFACE."
ip addr show dev "$IFACE"

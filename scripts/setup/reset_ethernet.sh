#!/usr/bin/env bash

#***********************************************************************
# Restore helmet Ethernet to automatic addressing for internet access
#***********************************************************************
# Preserve the LiDAR profile and activate the ordinary wired DHCP profile.
# Usage: sudo bash scripts/setup/reset_ethernet.sh [--help]
#***********************************************************************

set -euo pipefail

#***********************************************************************
# Help and argument parsing
#***********************************************************************

show_help() {
    cat <<'EOF'
Usage: sudo bash scripts/setup/reset_ethernet.sh [OPTIONS]

Restore eno1 to IPv4 DHCP and automatic IPv6 using "Wired connection 1".
Clear static addresses, routes, gateway, and DNS from that profile and accept
the network's automatic routes and DNS. Disable LiDAR autoconnect while
keeping its settings for later reuse. Activate the wired profile immediately.
Existing profiles are updated; missing profiles are created.

Options:
  -h, --help  Show this help message

Requires root, NetworkManager (nmcli), iproute2, and an eno1 interface.
Connect eno1 to a router/network providing DHCP before running this script.
Switching modes interrupts traffic on eno1. Run over WiFi or locally.
Logs: scripts/logs/

Example:
  sudo bash scripts/setup/reset_ethernet.sh
Restore LiDAR with: sudo bash scripts/setup/setup_lidar_ethernet.sh
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
CON_NAME="Wired connection 1"
LIDAR_CON_NAME="LiDAR"

if [[ "$EUID" -ne 0 ]]; then
    log_error "Run with sudo: sudo bash scripts/setup/reset_ethernet.sh"
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
# Configure and activate the DHCP profile
#***********************************************************************

if ! nmcli connection show id "$CON_NAME" >/dev/null 2>&1; then
    nmcli connection add type ethernet ifname "$IFACE" con-name "$CON_NAME" \
        connection.autoconnect no ipv4.method auto ipv6.method auto
fi

log_info "Restoring automatic addressing on $IFACE"
nmcli connection modify id "$CON_NAME" \
    connection.interface-name "$IFACE" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    ipv4.method auto \
    ipv4.addresses "" ipv4.gateway "" ipv4.routes "" \
    ipv4.dns "" ipv4.dns-search "" \
    ipv4.ignore-auto-dns no ipv4.ignore-auto-routes no \
    ipv4.never-default no ipv4.may-fail no \
    ipv6.method auto \
    ipv6.addresses "" ipv6.gateway "" ipv6.routes "" \
    ipv6.dns "" ipv6.dns-search "" \
    ipv6.ignore-auto-dns no ipv6.ignore-auto-routes no \
    ipv6.never-default no ipv6.may-fail yes

if nmcli connection show id "$LIDAR_CON_NAME" >/dev/null 2>&1; then
    nmcli connection modify id "$LIDAR_CON_NAME" connection.autoconnect no
fi

if ! nmcli --wait 60 connection up id "$CON_NAME" ifname "$IFACE"; then
    log_error "DHCP profile saved, but activation failed or timed out. Check the cable and DHCP server, then retry."
    exit 1
fi
log_success "Connection $CON_NAME is up on $IFACE."
ip addr show dev "$IFACE"
ip -4 route show dev "$IFACE"

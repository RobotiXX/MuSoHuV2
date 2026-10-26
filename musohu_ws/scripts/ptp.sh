#!/usr/bin/env bash
#***********************************************************************
# Configure software PTP serving on the dedicated MuSoHu LiDAR Ethernet link.
# Description: Phone/NTP owns host time; ptp4l serves it without adjusting the clock.
# Usage: ./ptp.sh [--install | --status | --stop] [--interface eno1]
# Examples: ./ptp.sh --status; ./ptp.sh --install --interface eno1
# Prerequisites: Ubuntu 22.04, systemd, sudo for installation/service changes.
# Author: MuSoHu Team
# Date: 2026-10-14
#***********************************************************************
set -euo pipefail
ptp_mode=--status
ptp_interface=eno1
while [[ $# -gt 0 ]]; do
    case "$1" in
        --install|--status|--stop) ptp_mode=$1; shift ;;
        --interface) [[ $# -ge 2 ]] || exit 2; ptp_interface=$2; shift 2 ;;
        -h|--help)
            cat <<'HELP'
Usage: ptp.sh [--install | --status | --stop] [--interface eno1]
  --install   Install linuxptp, copy the tested config and enable musohu-ptp.
  --status    Show interface timestamp capability, host NTP and service status.
  --stop      Stop and disable only musohu-ptp (uses sudo).
  --interface Dedicated wired LiDAR interface (default eno1).
Run as your normal user. Installation uses sudo. No network addresses,
hotspot settings or host NTP service are changed. No phc2sys is started.
Configure Helios TimeSyncSrc=PTP-E2E-L4, domain 0; verify Lock and real packet
timestamps before enabling use_lidar_clock in ROS. See README.md, Session clocks.
HELP
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
ptp_script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$ptp_script_dir/../../scripts/utils/logging_config.sh"
[[ "$ptp_interface" =~ ^[a-zA-Z0-9_.-]+$ && -d /sys/class/net/$ptp_interface ]] || {
    log_error 'Invalid or missing Ethernet interface.'; exit 2;
}
[[ ! -d /sys/class/net/$ptp_interface/wireless ]] || {
    log_error 'Use the dedicated wired LiDAR link, not WiFi.'; exit 2;
}
case "$ptp_mode" in
    --status)
        ethtool -T "$ptp_interface"
        timedatectl show -p NTPSynchronized -p NTP
        systemctl show musohu-ptp.service -p ActiveState -p SubState -p ExecMainStatus
        ;;
    --stop) sudo systemctl disable --now musohu-ptp.service ;;
    --install)
        sudo -v
        sudo apt-get update
        sudo apt-get install -y linuxptp ethtool
        sudo install -d -m 0755 /etc/musohu
        sudo install -m 0644 "$ptp_script_dir/../config/ptp4l.conf" /etc/musohu/ptp4l.conf
        ptp_unit=$(mktemp)
        trap 'rm -f "$ptp_unit"' EXIT
        cat > "$ptp_unit" <<UNIT
[Unit]
Description=MuSoHu software PTP source on $ptp_interface
After=network-online.target systemd-timesyncd.service
Wants=network-online.target

[Service]
Type=simple
RuntimeDirectory=musohu-ptp
ExecStart=/usr/sbin/ptp4l -f /etc/musohu/ptp4l.conf -i $ptp_interface -m -q
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
CapabilityBoundingSet=CAP_NET_BIND_SERVICE CAP_NET_RAW CAP_NET_ADMIN
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
UNIT
        sudo install -m 0644 "$ptp_unit" /etc/systemd/system/musohu-ptp.service
        sudo systemctl daemon-reload
        sudo systemctl enable musohu-ptp.service
        sudo systemctl restart musohu-ptp.service
        systemctl is-active --quiet musohu-ptp.service
        log_success 'PTP service started. Verify LiDAR lock and packet UTC before recording.'
        ;;
esac

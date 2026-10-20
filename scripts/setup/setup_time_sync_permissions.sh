#!/usr/bin/env bash
#***********************************************************************
# Install narrow offline-clock permissions and optional benchmark mode access.
# Description: Permit date/set-ntp; optionally allow three fixed nvpmodel modes.
# Usage: ./setup_time_sync_permissions.sh [--with-power-modes] [--help]
# Example: ./setup_time_sync_permissions.sh --with-power-modes
# Prerequisites: Run as normal Jetson user; sudo password required for install.
# Author: MuSoHu Team
# Date: 2026-10-15
#***********************************************************************
set -euo pipefail
permission_power=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-power-modes) permission_power=true; shift ;;
        -h|--help)
            cat <<'HELP'
Usage: setup_time_sync_permissions.sh [--with-power-modes]
Install /etc/sudoers.d/musohu-v2-controls for the invoking normal user:
  date -u -s @<epoch>; timedatectl set-ntp true/false.
Optional --with-power-modes also permits nvpmodel -m 0, 1, 3, but only after
checking those IDs are 15W, 25W, 7W on this host. It does not switch a mode,
change system time, restart services or change networking. Review this script
and the narrow allowed commands before installation. Existing rules remain.
The installed web unit must allow privilege elevation (NoNewPrivileges=false).
HELP
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
permission_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$permission_dir/../utils/logging_config.sh"
[[ $EUID -ne 0 ]] || { log_error 'Run as the normal web-service user; this helper uses sudo.'; exit 1; }
permission_user=$(id -un)
[[ "$permission_user" =~ ^[a-z_][a-z0-9_-]*$ ]] || { log_error 'Unsupported username'; exit 1; }
permission_file=$(mktemp)
trap 'rm -f "$permission_file"' EXIT
cat > "$permission_file" <<EOF
# MuSoHu v2: offline phone clock; no arbitrary root shell or service control.
$permission_user ALL=(root) NOPASSWD: /usr/bin/date -u -s @*, /usr/bin/timedatectl set-ntp false, /usr/bin/timedatectl set-ntp true
EOF
if $permission_power; then
    for pair in '0 15W' '1 25W' '3 7W'; do
        read -r permission_id permission_name <<< "$pair"
        rg -q "^< POWER_MODEL ID=$permission_id NAME=$permission_name >" /etc/nvpmodel.conf || {
            log_error 'Power-mode IDs differ; refusing to install guessed commands.'; exit 1;
        }
    done
    printf '%s ALL=(root) NOPASSWD: /usr/sbin/nvpmodel -m 0, /usr/sbin/nvpmodel -m 1, /usr/sbin/nvpmodel -m 3\n' "$permission_user" >> "$permission_file"
fi
sudo -v
sudo visudo -cf "$permission_file"
sudo install -m 0440 "$permission_file" /etc/sudoers.d/musohu-v2-controls
log_success 'Installed narrow permissions; time, network and power mode were not changed.'

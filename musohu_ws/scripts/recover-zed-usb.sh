#!/usr/bin/env bash
#***********************************************************************
# Inspect or rebind an otherwise empty USB 3 hub with a stuck ZED camera.
# Description: Targeted recovery for the observed USB protocol errors (-71).
# Usage: ./recover-zed-usb.sh [--check | --reset | -h | --help]
# Examples: ./recover-zed-usb.sh; ./recover-zed-usb.sh --reset
# Prerequisites: Linux sysfs; working sudo for --reset; sensor launches stopped.
# Author: MuSoHu Team
# Date: 2026-10-14
#***********************************************************************
set -euo pipefail
usb_recovery_mode=${1:---check}
case "$usb_recovery_mode" in
    -h|--help)
        cat <<'HELP'
Usage: recover-zed-usb.sh [--check | --reset | -h | --help]
  --check   Identify the ZED video device's parent USB 3 hub (default).
  --reset   Rebind that hub through Linux sysfs using sudo; all its USB 3
            children disconnect briefly. Refuses hubs containing other devices.
Run with sensor launches stopped, as your normal user. Does not reboot the
Jetson, reset its USB controller, or change persistent device/network settings.
This is a recovery attempt, not a guarantee that a failed port will recover.
If camera video does not return, inspect the cable/hub/power path and save the
kernel log before a planned host power cycle. See musohu_ws/VALIDATION.md.
HELP
        exit 0 ;;
    --check|--reset) ;;
    *) echo "Unknown option: $usb_recovery_mode" >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { echo 'Expected at most one option.' >&2; exit 2; }
usb_recovery_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$usb_recovery_dir/../../scripts/utils/logging_config.sh"
usb_recovery_unbound=false
usb_recovery_on_error() {
    if [[ "$usb_recovery_unbound" == true ]]; then
        printf '%s' "$usb_recovery_hub" | sudo tee /sys/bus/usb/drivers/usb/bind >/dev/null || true
    fi
    log_error 'USB recovery failed. Save kernel logs before further recovery.'
}
trap usb_recovery_on_error ERR

#***********************************************************************
# Validate the reset scope before requesting sudo or changing any device.
#***********************************************************************
usb_recovery_hub=$(python3 - <<'PY'
from pathlib import Path
import sys
root = Path('/sys/bus/usb/devices')
def value(device, field):
    return (device / field).read_text().strip()
cameras = [d for d in root.iterdir() if (d / 'idVendor').exists()
           and value(d, 'idVendor') == '2b03' and value(d, 'idProduct') == 'f880']
if len(cameras) != 1 or '.' not in cameras[0].name:
    sys.exit('Expected exactly one ZED USB video device behind a hub; no reset performed.')
hub = root / cameras[0].name.rsplit('.', 1)[0]
if value(hub, 'bDeviceClass') != '09' or float(value(hub, 'speed')) < 5000:
    sys.exit('Parent is not a USB 3 hub; no reset performed.')
for child in root.glob(hub.name + '.*'):
    if (child / 'idVendor').exists() and not (
            value(child, 'idVendor') == '2b03' and value(child, 'idProduct') == 'f880'):
        sys.exit(f'Other device on hub: {child.name}; refusing shared-hub reset.')
print(hub.name)
PY
)
log_info "Target: USB 3 hub $usb_recovery_hub; only ZED video descendants detected."
[[ "$usb_recovery_mode" == --reset ]] || exit 0
sudo -v
log_info 'Unbinding and rebinding the verified hub; USB video will disconnect briefly.'
printf '%s' "$usb_recovery_hub" | sudo tee /sys/bus/usb/drivers/usb/unbind >/dev/null
usb_recovery_unbound=true
printf '%s' "$usb_recovery_hub" | sudo tee /sys/bus/usb/drivers/usb/bind >/dev/null
usb_recovery_unbound=false
udevadm settle --timeout=10
log_info 'Hub rebind completed. Check video enumeration and retry the ZED launch.'
lsusb -t

#!/usr/bin/env bash
#***********************************************************************
# Install the hotspot boot service from this checkout.
# Description: Render its absolute script path, verify, install and enable.
# Usage: ./setup-hotspot-service.sh [--help]
# Example: sudo bash scripts/hotspot/setup-hotspot-service.sh
# Prerequisites: systemd, Python 3, NetworkManager; sudo for installation.
# Author: MuSoHu Team
# Date: 2026-10-21
#***********************************************************************
set -euo pipefail
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            cat <<'HELP'
Usage: setup-hotspot-service.sh [--help]
Install/enable hotspot.service using the start script in this checkout.
Does not start/restart the hotspot or disconnect the current Wi-Fi session.
On the next boot or explicit restart, the hotspot uses 10.42.0.1/24;
open http://10.42.0.1:8000 for the web app. NetworkManager provides DHCP/DNS.
Run as a normal user with sudo access, or as root.
HELP
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
hotspot_setup_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$hotspot_setup_dir/../utils/logging_config.sh"
trap 'log_error "Hotspot service installation failed at line $LINENO"' ERR
hotspot_setup_stage=$(mktemp -d)
trap 'rm -rf -- "$hotspot_setup_stage"' EXIT
python3 - "$hotspot_setup_dir" "$hotspot_setup_stage/hotspot.service" <<'PYTHON'
from pathlib import Path
import sys
source, destination = Path(sys.argv[1]), Path(sys.argv[2])
script = str(source/'start-hotspot.sh').replace('\\','\\\\').replace('"','\\"').replace('%','%%')
text = (source/'hotspot.service').read_text().replace('HOTSPOT_SCRIPT_PLACEHOLDER',script)
assert 'PLACEHOLDER' not in text
destination.write_text(text)
PYTHON
systemd-analyze verify "$hotspot_setup_stage/hotspot.service"
sudo install -m 0644 "$hotspot_setup_stage/hotspot.service" /etc/systemd/system/hotspot.service
sudo systemctl daemon-reload
sudo systemctl enable hotspot.service
log_success 'Hotspot boot service installed; current Wi-Fi connection unchanged.'

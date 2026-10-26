#!/usr/bin/env bash
#***********************************************************************
# Run the MuSoHu loopback-only Zenoh router with Stereolabs tuning.
# Description: Run or install the tuned loopback router used by the workspace.
#   Does not change network interfaces, clocks or hotspot settings.
# Usage: ./zenoh.sh --router | --install | --check
# Options: --router runs; --install enables service; --check waits for listener.
# Example: ./musohu_ws/scripts/zenoh.sh --router
# Prerequisites: ROS 2 Humble and ros-humble-rmw-zenoh-cpp (setup.sh installs it).
# Author: MuSoHu Team
# Date: 2026-10-23
#***********************************************************************
set -euo pipefail
zenoh_mode=${1:---help}
case "$zenoh_mode" in
    -h|--help)
        cat <<'HELP'
Usage: zenoh.sh --router | --install | --check
  --router   Run a foreground tuned router on 127.0.0.1:7447.
  --install  Install/enable the boot service using sudo (run as normal user).
  --check    Wait up to 15 seconds for the loopback router listener.
Zenoh is the workspace default. setup.sh installs its service; use --router
only when the service is not running. Explicit RMW_IMPLEMENTATION overrides
remain supported. HTTP and the native LiDAR link are unaffected.
HELP
        exit 0 ;;
    --router|--install|--check) [[ $# -eq 1 ]] || { echo 'Unexpected arguments; use --help.' >&2; exit 2; } ;;
    *) echo "Unknown option: $1; use --help." >&2; exit 2 ;;
esac
#***********************************************************************
# Load libraries, set router-specific endpoints and preserve foreground ownership.
#***********************************************************************
zenoh_script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$zenoh_script_dir/../../scripts/utils/logging_config.sh"
if [[ "$zenoh_mode" == --check ]]; then
    exec /usr/bin/python3 - <<'PY_CHECK'
import socket,time
end=time.monotonic()+15
while time.monotonic()<end:
    try:
        with socket.create_connection(('127.0.0.1',7447),timeout=.2): pass
        raise SystemExit(0)
    except OSError: time.sleep(.1)
raise SystemExit('Zenoh router is not listening on 127.0.0.1:7447')
PY_CHECK
fi
if [[ "$zenoh_mode" == --install ]]; then
    [[ $EUID -ne 0 ]] || { log_error 'Run as normal user; the installer uses sudo.'; exit 1; }
    [[ -x /opt/ros/humble/lib/rmw_zenoh_cpp/rmw_zenohd ]] || {
        log_error 'Install ros-humble-rmw-zenoh-cpp first.'; exit 1;
    }
    zenoh_unit=$(mktemp)
    trap 'rm -f "$zenoh_unit"' EXIT
    /usr/bin/python3 - "$zenoh_script_dir" "$zenoh_unit" <<'PY_UNIT'
from pathlib import Path
import getpass,grp,os,sys
scripts=Path(sys.argv[1]); root=scripts.parents[1]
s=(root/'scripts/deploy/templates/musohu-zenoh.service.template').read_text()
for k,v in {'USER':getpass.getuser(),'GROUP':grp.getgrgid(os.getgid()).gr_name,
            'WORKSPACE':str(scripts.parent)}.items():
    s=s.replace(k+'_PLACEHOLDER',v.replace('\\','\\\\').replace('"','\\"').replace('%','%%'))
Path(sys.argv[2]).write_text(s)
PY_UNIT
    sudo install -m 0644 "$zenoh_unit" /etc/systemd/system/musohu-zenoh.service
    sudo systemctl daemon-reload
    # Starting is idempotent; do not restart a router serving active sessions.
    sudo systemctl enable --now musohu-zenoh.service
    "$0" --check
    log_success 'MuSoHu Zenoh router service installed and listening.'
    exit 0
fi
[[ -f /opt/ros/humble/setup.bash ]] || { log_error 'ROS 2 Humble is missing.'; exit 1; }
set +u
source /opt/ros/humble/setup.bash
set -u
zenoh_binary=/opt/ros/humble/lib/rmw_zenoh_cpp/rmw_zenohd
[[ -x "$zenoh_binary" ]] || { log_error 'Run setup.sh --deps-only to install Zenoh.'; exit 1; }
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ROS_LOCALHOST_ONLY=1
export ZENOH_ROUTER_CHECK_ATTEMPTS=0
export RMW_ZENOH_BUFFER_POOL_MAX_SIZE_BYTES=33554432
export ZENOH_CONFIG_OVERRIDE='listen/endpoints=["tcp/127.0.0.1:7447"];connect/endpoints=[];scouting/multicast/enabled=false;transport/shared_memory/enabled=true;transport/link/tx/queue/congestion_control/drop/wait_before_drop=1000000'
log_info 'Starting loopback-only Zenoh router on 127.0.0.1:7447 with Stereolabs tuning.'
exec "$zenoh_binary"

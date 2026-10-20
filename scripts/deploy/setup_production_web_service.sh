#!/usr/bin/env bash
#***********************************************************************
# Prepare or install the MuSoHu FastAPI service for this checkout.
# Description: Create its venv and render a reviewable systemd service first.
# Usage: ./setup_production_web_service.sh [--prepare-only | --install] [--port N]
# Examples: ./setup_production_web_service.sh --prepare-only --port 8001
# Prerequisites: Python 3.10 / python3-venv, built ROS workspace; sudo for install.
# Author: MuSoHu Team
# Date: 2026-10-14
#***********************************************************************
set -euo pipefail
web_setup_mode=prepare
web_setup_port=8000
while [[ $# -gt 0 ]]; do
    case "$1" in
        --prepare-only) web_setup_mode=prepare; shift ;;
        --install) web_setup_mode=install; shift ;;
        --port) [[ $# -ge 2 ]] || exit 2; web_setup_port=$2; shift 2 ;;
        -h|--help)
            cat <<'HELP'
Usage: setup_production_web_service.sh [--prepare-only | --install] [--port N]
  --prepare-only  Create venv, install requirements and render the service (default).
  --install       Also install/enable/restart musohu-web using sudo.
  --port N        HTTP port, 1024–65535 (default 8000).
Run as your normal user. Prepare does not replace the existing service.
Installation selects this checkout and replaces the current musohu-web unit.
No hotspot, DNS, firewall or network configuration is changed.
The ROS workspace must already be built with musohu_ws/scripts/setup.sh.
See web-app/README.md for preview, dummy publishers and tests.
HELP
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
[[ $EUID -ne 0 ]] || { echo 'Run as your normal user; --install uses sudo.' >&2; exit 1; }
[[ "$web_setup_port" =~ ^[0-9]{4,5}$ ]] && (( web_setup_port >= 1024 && web_setup_port <= 65535 )) || {
    echo 'Port must be between 1024 and 65535.' >&2; exit 2;
}
web_setup_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
web_setup_root=$(cd -- "$web_setup_dir/../.." && pwd)
web_setup_app=$web_setup_root/web-app
source "$web_setup_root/scripts/utils/logging_config.sh"
trap 'log_error "Web setup failed at line $LINENO; see $LOG_FILE"' ERR
[[ -f "$web_setup_root/musohu_ws/install/setup.bash" ]] || {
    log_error 'Build musohu_ws before preparing the web service.'; exit 1;
}
[[ -x "$web_setup_app/venv/bin/python" ]] || python3 -m venv "$web_setup_app/venv"
"$web_setup_app/venv/bin/python" -m pip install -r "$web_setup_app/requirements.txt"
mkdir -p "$web_setup_app/logs" "$web_setup_app/deploy"
"$web_setup_app/venv/bin/python" - "$web_setup_dir" "$web_setup_root" "$web_setup_port" <<'PY'
from pathlib import Path
import getpass,grp,os,sys
scripts,root,port=sys.argv[1:]
root=Path(root)
text=(Path(scripts)/'templates/musohu-web.service.template').read_text()
values={'USER':getpass.getuser(),'GROUP':grp.getgrgid(os.getgid()).gr_name,
        'WEB_APP_DIR':str(root/'web-app'),'WORKSPACE':str(root/'musohu_ws'),'PORT':port}
for key,value in values.items():
    text=text.replace(key+'_PLACEHOLDER',value.replace('\\','\\\\').replace('"','\\"').replace('%','%%'))
assert 'PLACEHOLDER' not in text
(root/'web-app/deploy/musohu-web.service').write_text(text)
PY
systemd-analyze verify "$web_setup_app/deploy/musohu-web.service"
log_success "Prepared service: $web_setup_app/deploy/musohu-web.service"
if [[ "$web_setup_mode" == install ]]; then
    "$web_setup_root/scripts/setup/setup_time_sync_permissions.sh"
    sudo install -m 0644 "$web_setup_app/deploy/musohu-web.service" /etc/systemd/system/musohu-web.service
    sudo systemctl daemon-reload
    sudo systemctl enable musohu-web.service
    sudo systemctl restart musohu-web.service
    for attempt in {1..30}; do
        if curl --fail --silent "http://127.0.0.1:$web_setup_port/api/health" >/dev/null; then
            log_success "Web service healthy on port $web_setup_port"; exit 0
        fi
        sleep 1
    done
    log_error 'Health check failed; inspect journalctl -u musohu-web.'; exit 1
fi

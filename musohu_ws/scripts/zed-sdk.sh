#!/usr/bin/env bash
#***********************************************************************
# Download or install the MuSoHu ZED SDK 5.5 for Jetson L4T 36.4.
# Usage: ./zed-sdk.sh [--download | --install | --help]
# Downloads are cached; --install backs up the existing SDK first.
# Author: MuSoHu Team
# Date: 2026-10-12
#***********************************************************************
set -euo pipefail

show_help() {
    cat <<'HELP'
Usage: zed-sdk.sh [--download | --install | -h | --help]
  --download  Download SDK 5.5 for L4T36.4/CUDA12.6 and verify its archive (default).
  --install   Back up /usr/local/zed, then run the official SDK installer.
              Run in a normal terminal with working sudo. Keeps CUDA/JetPack;
              skips GMSL drivers and Python API (ROS uses the C++ API).
  -h, --help  Show help.
Cache: ${XDG_CACHE_HOME:-$HOME/.cache}/musohu/zed-sdk
Backup: cache/backup-<timestamp>-<pid>/zed
After installation, rebuild musohu_ws and validate GEN_3 on the actual camera.
HELP
}

mode=${1:---download}
case "$mode" in
    -h|--help) show_help; exit 0 ;;
    --download|--install) ;;
    *) show_help >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { show_help >&2; exit 2; }
[[ $(uname -m) == aarch64 ]] || { echo 'Requires a Jetson aarch64 host.' >&2; exit 1; }
grep -q '^# R36 .*REVISION: 4\.' /etc/nv_tegra_release || {
    echo 'This installer is pinned to L4T36.4; choose the matching SDK for other hosts.' >&2
    exit 1
}
cache_dir=${XDG_CACHE_HOME:-$HOME/.cache}/musohu/zed-sdk
installer=$cache_dir/ZED_SDK_Tegra_L4T36.4_v5.5.run
mkdir -p "$cache_dir"
if [[ ! -f "$installer" ]]; then
    curl -fL --retry 3 --output "$installer.partial" \
        https://download.stereolabs.com/zedsdk/5.5/l4t36.4/jetsons
    mv "$installer.partial" "$installer"
fi
bash "$installer" --check
sha256sum "$installer" > "$installer.sha256"
echo "Verified installer: $installer"
[[ "$mode" == --install ]] || exit 0
# Check elevation before touching the existing installation.
sudo -v
backup_dir=$cache_dir/backup-$(date +%Y%m%dT%H%M%S)-$$
if [[ -d /usr/local/zed ]]; then
    mkdir -p "$backup_dir"
    cp -a /usr/local/zed "$backup_dir/zed"
    echo "Previous SDK backed up to $backup_dir/zed"
fi
bash "$installer" --quiet --nox11 -- --silent --skip_cuda --skip_drivers --skip_python
grep -q 'PACKAGE_VERSION "5\.5\.' /usr/local/zed/zed-config-version.cmake || {
    echo 'SDK 5.5 installation did not complete. Inspect installer output.' >&2
    exit 1
}
echo 'SDK 5.5 installed. Rebuild musohu_ws in a fresh ROS 2 Humble shell.'

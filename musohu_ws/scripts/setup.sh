#!/usr/bin/env bash
#***********************************************************************
# Install MuSoHu sensor dependencies and build the ROS 2 workspace.
# Description: Ubuntu 22.04 / ROS 2 Humble / Jetson L4T 36.4 setup.
# Usage: ./setup.sh [--deps-only | --build-only] [--skip-sdk] [--skip-udev]
# Examples: ./setup.sh; ./setup.sh --deps-only; ./setup.sh --build-only
# Prerequisites: ROS 2 Humble apt repository and underlay; working sudo for deps.
# Author: MuSoHu Team
# Date: 2026-10-14
#***********************************************************************
set -euo pipefail

#***********************************************************************
# Help / argument parsing (no system changes for --help).
#***********************************************************************
show_help() {
    cat <<'HELP'
Usage: setup.sh [--deps-only | --build-only] [--skip-sdk] [--skip-udev]
  Default        Initialize pinned submodules, install dependencies, then build.
  --deps-only    Install apt/rosdep/Python dependencies, SDK and device rules.
  --build-only   Initialize pinned submodules and build; does not use sudo.
  --skip-sdk     Keep the installed SDK (build still requires SDK 5.5).
  --skip-udev    Do not install/reload device rules.
  -h, --help     Show this help.

Run as your normal user in a fresh terminal. Dependency installation uses sudo;
do not run the entire script as root. Requires Ubuntu 22.04 and an installed
ROS 2 Humble underlay with its apt repository configured. For a clean host see
https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html first.
JetPack/CUDA, network addresses and firmware are not reconfigured.
Dependencies include the verified MCAP CLI and a loopback-only Zenoh boot service.
The SDK helper installs 5.5 only if missing; it keeps the current CUDA/JetPack.

Builds always use --symlink-install, sequential packages and one compiler job.
Re-run --build-only after changing source/config. Logs: scripts/logs/.
Examples:
  ./musohu_ws/scripts/setup.sh
  ./musohu_ws/scripts/setup.sh --deps-only --skip-sdk
  ./musohu_ws/scripts/setup.sh --build-only
HELP
}
setup_mode=all
setup_skip_sdk=false
setup_skip_udev=false
for arg in "$@"; do
    case "$arg" in
        -h|--help) show_help; exit 0 ;;
        --deps-only|--build-only)
            [[ "$setup_mode" == all ]] || { echo 'Choose one mode.' >&2; exit 2; }
            setup_mode=${arg#--} ;;
        --skip-sdk) setup_skip_sdk=true ;;
        --skip-udev) setup_skip_udev=true ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

#***********************************************************************
# Configuration and preflight.
#***********************************************************************
setup_script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
setup_ws_dir=$(cd -- "$setup_script_dir/.." && pwd)
setup_repo_dir=$(cd -- "$setup_ws_dir/.." && pwd)
source "$setup_repo_dir/scripts/utils/logging_config.sh"
trap 'log_error "Setup failed at line $LINENO. See $LOG_FILE"' ERR
[[ $EUID -ne 0 ]] || { log_error 'Run as your normal user; sudo is used for apt only.'; exit 1; }
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 22.04 ]] || {
    log_error 'This setup targets Ubuntu 22.04 / ROS 2 Humble.'; exit 1;
}
[[ -f /opt/ros/humble/setup.bash ]] || {
    log_error 'Install the ROS 2 Humble underlay first; see setup.sh --help.'; exit 1;
}
# Inherited overlays can mask missing dependencies or select the old workspace.
for setup_prefix in ${AMENT_PREFIX_PATH//:/ }; do
    [[ "$setup_prefix" == /opt/ros/humble ]] || {
        log_error "Overlay already sourced: $setup_prefix. Use a fresh terminal."; exit 1;
    }
done
set +u
source /opt/ros/humble/setup.bash
set -u
cd "$setup_repo_dir"
git submodule update --init --recursive

#***********************************************************************
# Native, ROS, SDK and Python dependencies.
#***********************************************************************
if [[ "$setup_mode" != build-only ]]; then
    if ! sudo -n true 2>/dev/null; then sudo -v; fi
    sudo apt-get update
    sudo apt-get install -y build-essential cmake git curl zstd pkg-config \
        python3-colcon-common-extensions python3-rosdep python3-pip python3-venv \
        python3-numpy python3-yaml python3-usb python3-spidev python3-pyaudio \
        portaudio19-dev libusb-1.0-0-dev nlohmann-json3-dev linuxptp ethtool \
        ros-humble-ros-base ros-humble-rosbag2 ros-humble-rosbag2-storage-default-plugins \
        ros-humble-rosbag2-storage-mcap ros-humble-rmw-zenoh-cpp ros-humble-zed-description
    "$setup_script_dir/mcap-cli.sh" --install
    "$setup_script_dir/zenoh.sh" --install
    [[ -f /etc/ros/rosdep/sources.list.d/20-default.list ]] || sudo rosdep init
    rosdep update --rosdistro humble
    # Jammy supplies spidev via apt above; the driver's legacy key is unresolved.
    rosdep install --from-paths "$setup_ws_dir/src" --ignore-src --rosdistro humble \
        -y -t build -t buildtool -t exec --skip-keys python3-spidev
    # The USB pixel ring dependency has no Jammy apt/rosdep package. Its other
    # dependencies (PyUSB/spidev) come from apt; do not replace those with pip.
    python3 -m pip install --user --no-deps 'pixel-ring==0.1.0'
    if [[ "$setup_skip_sdk" == false ]] &&
        ! grep -q 'PACKAGE_VERSION "5\.5\.' /usr/local/zed/zed-config-version.cmake 2>/dev/null; then
        "$setup_script_dir/zed-sdk.sh" --install
    fi
    if [[ "$setup_skip_udev" == false ]]; then
        sudo install -m 0644 "$setup_repo_dir"/scripts/udev_rules/rules/*.rules /etc/udev/rules.d/
        sudo udevadm control --reload-rules
        log_info 'Device rules installed. Reconnect USB devices if permissions need refreshing.'
    fi
    python3 -c 'import usb.core, pyaudio, pixel_ring, spidev, numpy, tf_transformations'
    rosdep check --from-paths "$setup_ws_dir/src" --ignore-src --rosdistro humble \
        -t build -t buildtool -t exec --skip-keys python3-spidev
    log_success 'Dependencies installed.'
fi

#***********************************************************************
# Build and report. Never source an older workspace for this build.
#***********************************************************************
if [[ "$setup_mode" != deps-only ]]; then
    dpkg-query -W -f='${Status}' nlohmann-json3-dev 2>/dev/null | grep -q 'install ok installed' || {
        log_error 'Install native dependencies first: setup.sh --deps-only'; exit 1;
    }
    grep -q 'PACKAGE_VERSION "5\.5\.' /usr/local/zed/zed-config-version.cmake || {
        log_error 'SDK 5.5 is required; run setup.sh --deps-only.'; exit 1;
    }
    cd "$setup_ws_dir"
    colcon list --base-paths src
    # Clear the old temporary JSON CMake lookup without rebuilding unrelated
    # packages from scratch. The native package now supplies headers/config.
    MAKEFLAGS='-j1 -l1' CMAKE_BUILD_PARALLEL_LEVEL=1 \
        colcon build --base-paths src --symlink-install --executor sequential \
        --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
        -DBUILD_EXAMPLES=OFF -DBUILD_DOCS=OFF -Unlohmann_json_DIR -DZED_DIR=/usr/local/zed
    log_success "Build complete. In your terminal: source $setup_ws_dir/install/setup.bash"
fi

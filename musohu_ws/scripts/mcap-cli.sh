#!/usr/bin/env bash
#***********************************************************************
# Install the pinned official MCAP CLI for lossless post-record compression.
# Description: Downloads release 0.4.0 and verifies its published SHA-256.
# Usage: ./mcap-cli.sh --install | --check
# Options: --install uses sudo; --check reports version; --help changes nothing.
# Example: ./musohu_ws/scripts/mcap-cli.sh --install
# Prerequisites: curl, sha256sum, Ubuntu Linux arm64/amd64, working sudo.
# Author: MuSoHu Team
# Date: 2026-10-23
#***********************************************************************
set -euo pipefail
case "${1:---help}" in
    -h|--help)
        echo 'Usage: mcap-cli.sh --install | --check'
        echo 'Install verified MCAP CLI 0.4.0 to /usr/local/bin/mcap, or show its version.'
        exit 0 ;;
    --check) exec /usr/local/bin/mcap --version ;;
    --install) [[ $# -eq 1 ]] || { echo 'Use --help.' >&2; exit 2 ; } ;;
    *) echo "Unknown option: $1; use --help." >&2; exit 2 ;;
esac
mcap_script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$mcap_script_dir/../../scripts/utils/logging_config.sh"
case "$(uname -m)" in
    aarch64|arm64)
        mcap_arch=arm64
        mcap_hash=94fd84e40ed1593205caf9b9ccee863181256a2fe1ad051ee55d31b4d1b4aca7 ;;
    x86_64|amd64)
        mcap_arch=amd64
        mcap_hash=3ace13bc8f0273c69742f25695f7f2df84aed57ddd7c36d5f9a59561dc719fb1 ;;
    *) log_error 'Only Linux arm64 and amd64 are supported.'; exit 1 ;;
esac
if [[ -x /usr/local/bin/mcap ]] &&
    [[ $(sha256sum /usr/local/bin/mcap | cut -d' ' -f1) == "$mcap_hash" ]]; then
    log_success 'Pinned MCAP CLI is already installed.'; exit 0
fi
mcap_download=$(mktemp)
trap 'rm -f "$mcap_download"' EXIT
curl --fail --location --retry 2 \
    "https://github.com/foxglove/mcap/releases/download/releases/mcap-cli/v0.4.0/mcap-linux-$mcap_arch" \
    --output "$mcap_download"
[[ $(sha256sum "$mcap_download" | cut -d' ' -f1) == "$mcap_hash" ]] || {
    log_error 'MCAP download checksum mismatch.'; exit 1;
}
sudo install -m 0755 "$mcap_download" /usr/local/bin/mcap
/usr/local/bin/mcap --version
log_success 'Verified MCAP CLI installed.'

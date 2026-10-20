#!/usr/bin/env bash
#***********************************************************************
# Record the sensor/odometry topics needed for MuSoHu IMU comparisons.
# Usage: ./record-evaluation.sh [--topics FILE] [--output DIR] [--label NAME]
# Ctrl-C reaches ros2 directly so rosbag can flush and close normally.
# Author: MuSoHu Team
# Date: 2026-10-12
#***********************************************************************
set -euo pipefail

show_help() {
    cat <<'HELP'
Usage: record-evaluation.sh [--topics FILE] [--output DIR] [--label NAME]
  --topics FILE  YAML manifest with a nonempty string list named topics.
  --output DIR   Parent directory (default: ~/helmet_bags).
  --label NAME   Route/session label using letters, digits, underscores or hyphens.
  -h, --help     Show help.
Source /opt/ros/humble/setup.bash and musohu_ws/install/setup.bash first.
Metadata is saved beside the bag as <bag-name>.session.json. It describes the
requested recording, not proof that each topic published. Stop with Ctrl-C,
then check ros2 bag info, message counts and replay before evaluating.
HELP
}

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd -- "$script_dir/../.." && pwd)
manifest=$script_dir/../src/helmet_bringup/config/recording_topics.yaml
output_dir=$HOME/helmet_bags
label=walk
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) show_help; exit 0 ;;
        --topics|--output|--label)
            [[ $# -ge 2 ]] || { show_help >&2; exit 2; }
            case "$1" in
                --topics) manifest=$2 ;;
                --output) output_dir=$2 ;;
                --label) label=$2 ;;
            esac
            shift 2 ;;
        *) show_help >&2; exit 2 ;;
    esac
done
[[ "$label" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Invalid session label.' >&2; exit 2; }
command -v ros2 >/dev/null || { echo 'Source ROS 2 Humble and the workspace first.' >&2; exit 1; }
# Validate before creating metadata; preserve arbitrary topic strings as arguments.
topics_text=$(python3 - "$manifest" <<'PY'
import sys, yaml
data = yaml.safe_load(open(sys.argv[1]))
topics = data.get('topics') if isinstance(data, dict) else None
if not isinstance(topics, list) or not topics or any(
    not isinstance(t, str) or not t.startswith('/') or any(c.isspace() for c in t)
    for t in topics
):
    raise SystemExit('Manifest must contain a nonempty list of absolute ROS topic names.')
print('\n'.join(dict.fromkeys(topics)))
PY
)
mapfile -t topics <<< "$topics_text"
mkdir -p "$output_dir"
bag_path=$output_dir/${label}_$(date +%Y%m%d_%H%M%S)_$$
python3 - "$repo_dir" "$manifest" "$bag_path" "$label" <<'PY'
import datetime, json, pathlib, subprocess, sys, yaml
repo, manifest, bag, label = sys.argv[1:]
def git(*args):
    return subprocess.check_output(['git', '-C', repo, *args], text=True).strip()
sdk = pathlib.Path('/usr/local/zed/zed-config-version.cmake')
metadata = {
    'recording_requested_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'label': label, 'bag_path': str(pathlib.Path(bag).resolve()),
    'topics': yaml.safe_load(open(manifest))['topics'],
    'repository_commit': git('rev-parse', 'HEAD'),
    'repository_status': git('status', '--short'),
    'submodules': git('submodule', 'status', '--recursive'),
    'zed_sdk': sdk.read_text().splitlines()[0] if sdk.exists() else None,
    'note': 'Request metadata; verify actual topic counts and timestamps in the finished bag.',
}
pathlib.Path(bag + '.session.json').write_text(json.dumps(metadata, indent=2) + '\n')
PY
echo "Recording to $bag_path; stop with Ctrl-C."
exec ros2 bag record -o "$bag_path" "${topics[@]}"

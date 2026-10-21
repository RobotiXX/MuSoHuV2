# MuSoHu ROS 2 workspace

ROS 2 Humble sensor bringup for the Jetson Orin Nano, ZED 2i, Helios H32F70,
WT901 and ReSpeaker. `helmet_bringup` is the project-owned integration package.
The main research/backlog decisions are in [../TODO.md](../TODO.md).
See [VALIDATION.md](VALIDATION.md) for tested versions and remaining hardware checks.
On 2026-10-14, native setup and all 16 package builds passed. After reboot,
the complete rig passed short acquisition, web recording and playback checks,
including ZED GEN_3, RGB/depth, IMUs, LiDAR and timestamped audio. Software PTP
on the dedicated Ethernet link now drives native Helios timestamps. These
checks do not establish drift, calibration or sustained outdoor performance.
See [TIME_SYNC.md](TIME_SYNC.md), the [web workflow](../web-app/README.md) and
[depth/power tests](POWER_BENCHMARK.md).

## Reproducible source layout

| Path | Source | Branch/base |
| --- | --- | --- |
| `src/zed-ros2-wrapper` | RobotiXX fork | `musohu-v2` from `main` |
| `src/witmotion_IMU_ros` | RobotiXX Elettra fork | `musohu-v2` from `robotixx-ros2-humble` |
| `src/audio_common` | RobotiXX fork | `musohu-v2` from `ros2` |
| `src/respeaker_ros` | RobotiXX fork | `musohu-v2` from `master` (already ROS 2) |
| `src/rslidar_sdk` | RobotiXX fork | `musohu-v2` from `main` (ROS 1/2) |
| `src/rslidar_sdk/src/rs_driver` | RobotiXX nested fork | `musohu-v2` from `main` |
| `src/rslidar_msg` | RobotiXX fork | `musohu-v2` from `master` (ROS 2 manifest) |
| `src/zed-ros2-description` | Stereolabs upstream | pinned commit `22468247c1653d08a1e213809f3e9ce76291487d` |

All sensor drivers now use individual forks; the transitional bundled workspace
and source symlinks have been removed. Build `src` to discover 16 packages.
`rs_driver` is built inside `rslidar_sdk`, not as a separate ROS package.
The independent `~/ros2_musohu_ws` reference remains untouched.

Submodule gitlinks pin exact source revisions; `branch = musohu-v2` does not
make ordinary initialization advance to the latest branch tip.

```bash
git submodule update --init --recursive
git submodule status --recursive
```

## Host and SDK setup

Inspected 2026-10-12: Ubuntu 22.04.5, aarch64 Jetson Orin Nano Super 8 GB,
L4T 36.4.7, CUDA 12.6, ROS 2 Humble. **ZED SDK 5.5.0 is now installed**,
upgraded from 5.1.0. The 5.1 backup was removed at the maintainer's request.
Use **SDK 5.5 for L4T 36.4**, matching the existing OS/CUDA; an OS/JetPack
upgrade is not required. [Official SDK downloads and release notes](https://www.stereolabs.com/developers/release/5.5).

In a fresh normal terminal, run the unified setup from the repository root:

```bash
./musohu_ws/scripts/setup.sh
# Or separate installation and compilation:
./musohu_ws/scripts/setup.sh --deps-only
./musohu_ws/scripts/setup.sh --build-only
```

The helper initializes pinned submodules, installs apt and rosdep dependencies,
provisions `pixel-ring==0.1.0` in the user's Python environment, installs device
rules, retains SDK 5.5 if present and builds sequentially with `--symlink-install`.
Use `--skip-sdk` or `--skip-udev` when those steps are managed separately.
It requires Ubuntu 22.04, the ROS 2 Humble underlay and its apt repository;
[configure those first on a clean host](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html).
It does not flash JetPack, change CUDA, configure LiDAR networking or deploy
the web service. Full clean-machine provisioning remains to be validated.

`nlohmann-json3-dev` supplies header-only C++ JSON parsing and its CMake package.
The pinned ZED wrapper calls `find_package(nlohmann_json REQUIRED)` and compiles
JSON/GNSS replay helpers even with GNSS disabled. It is a build dependency;
there is no JSON daemon to run. The setup helper installs it using
`sudo apt-get install -y nlohmann-json3-dev`; the earlier temporary extracted
headers are no longer the intended setup. The manifest's `nlohmann-json-dev`
rosdep key resolves to this Ubuntu package.

The ReSpeaker manifest's `python3-spidev` rosdep key is unresolved, so setup
installs the Jammy apt package explicitly and skips only that rosdep key.
Other Python/audio dependencies are checked, and `zed_msgs` is installed through
rosdep; it must match wrapper 5.5.

The SDK script verifies the installer, saves its SHA256 and backs up the old
SDK before installation. It skips CUDA replacement, GMSL driver installation
(the 2i is USB) and the Python API. SDK 5.5 may download/re-optimize models on
first use; allow network access and warm up before recording experiments.

## Build

Use a fresh terminal; source the Humble underlay without the old workspace.

```bash
source /opt/ros/humble/setup.bash
cd musohu_ws
colcon list --base-paths src
MAKEFLAGS='-j1 -l1' CMAKE_BUILD_PARALLEL_LEVEL=1 colcon build --base-paths src --symlink-install \
  --executor sequential --cmake-args -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=OFF -DBUILD_EXAMPLES=OFF -DBUILD_DOCS=OFF
source install/setup.bash
ros2 launch helmet_bringup helmet_sensors.launch.py --show-args
```

## Local ROS communication

Sourcing this workspace sets `ROS_LOCALHOST_ONLY=1`: ROS topics, services,
actions and discovery stay on the Jetson. The web app enforces the same setting
for its sensor and recording children, and the systemd template includes it.
The current Jetson user's `~/.bashrc` also sets it for new terminal sessions.
In a terminal that was already open, source the workspace again or run:

```bash
export ROS_LOCALHOST_ONLY=1
ros2 daemon stop
```

Restart any ROS nodes started before the setting changed. Local CLI, RViz,
recorders and sensor nodes must use the same ROS domain. Browser access to the
web app over Wi-Fi still works; LiDAR UDP input and PTP on `eno1` continue
normally. Run ROS inspection tools on the Jetson rather than another laptop.
See the [Humble environment guide](https://docs.ros.org/en/humble/Tutorials/Beginner-CLI-Tools/Configuring-ROS2-Environment.html#the-ros-localhost-only-variable).

## Bringup

```bash
# Entire rig (requires devices and LiDAR networking):
ros2 launch helmet_bringup helmet_sensors.launch.py
# Individual sensors:
ros2 launch helmet_bringup zed.launch.py
ros2 launch helmet_bringup imu.launch.py device:=witImu baud:=115200
ros2 launch helmet_bringup lidar.launch.py
ros2 launch helmet_bringup audio.launch.py
# Camera only through the combined entry point:
ros2 launch helmet_bringup helmet_sensors.launch.py \
  launch_imu:=false launch_lidar:=false launch_audio:=false
```

The old `/action` estimator is opt-in with `launch_actions:=true`; it assumes
the default ZED namespace. The combined launch also publishes the **finalized
sensor extrinsics** from `zed2i_camera_link` to `rslidar` and `imu_link`,
confirmed accurate and final by the maintainer on 2026-10-21 in commit
`2c33979`. Canonical values are in `config/sensor_extrinsics.yaml`; the IMU
frame origin is the housing center. Use these values for the current rig.
Set `launch_static_tf:=false` to disable publication, or use
`extrinsics_file:=/absolute/path/to/extrinsics.yaml` for a different hardware geometry.
The WT901 port uses Qt's device name (`witImu`, not a copied `/dev/ttyUSB1`
assumption); `baud` must match sensor firmware.
The pinned WitMotion fork includes a shutdown fix: ROS shutdown is not called recursively,
the executor thread is joined, and publishers/services are released before
process teardown. Its regression test runs without attached hardware:

```bash
python3 -m unittest discover -s src/witmotion_IMU_ros/test -v
python3 -m unittest discover -s src/respeaker_ros/test -p test_sensor_output.py -v
python3 -m unittest discover -s src/rslidar_sdk/test -p test_shutdown.py -v
```

ZED uses `ros_params_override_path`, retaining upstream camera/common defaults.
The profile selects **GEN_3** with IMU fusion, area memory/loop closure and
gravity alignment. Full 3D tracking suits a moving helmet; floor alignment,
2D mode and static-camera mode are disabled. `PREFER_GPU` selects SDK 5.5's
faster tracking option. The nominal profile captures HD720 at 30 Hz, requests
30 Hz image publication, and records left/right **JPEG compressed images**
plus both calibrations. Dense depth is disabled (`NONE`); 24-bit BGR output
is enabled. Both calibrated and raw ZED IMUs are recorded independently at
about 200 Hz (`sensors_image_sync: false`). Image sync would couple IMU output
to image publication and can suppress it without image subscribers. Requested
image rate is a cap, not a performance guarantee: the full-rig JPEG pilot
recorded about 16.6 Hz per image, while odometry remained about 29.4 Hz.
[Tracking modes](https://docs.stereolabs.com/docs/development/zed-sdk/modules/positional-tracking/modes),
[ROS tracking parameters](https://docs.stereolabs.com/docs/integrations/ros-2/positional-tracking).

Odometry is kept continuous across loop closures; corrected poses use `map`.
`/zed2i/zed_node/odom` is `nav_msgs/Odometry`: its pose is relative to `odom`,
with twist, covariance and a camera child frame. `/zed2i/zed_node/pose` is
`geometry_msgs/PoseStamped`: the camera pose relative to `map`, including
area-memory/loop-closure corrections. Thus pose can jump after relocalization
while odometry stays continuous with `reset_odom_with_loop_closure: false`.
The two poses need not be numerically equal. Record both to compare local
motion against globally corrected trajectories; `map→odom` links their frames.
When integrating another estimator, disable ZED TF publication as appropriate
with `publish_tf:=false publish_map_tf:=false` in the individual ZED launch.
Do not create two publishers for the same TF edge.

The nominal workflow runs no dense depth. GEN_3 still computes VIO; disabling
depth does not disable tracking. Point cloud, mapping, body and object
detection remain disabled. `imu/data` carries SDK calibrated measurements
and orientation; `imu/data_raw` carries uncalibrated acceleration/gyro without
an orientation estimate. JPEG is lossy; the installed plugin used quality 95
on both cameras, captured in recording metadata. Validate image quality for
future offline depth/odometry processing.

The old **15 Hz uncompressed stereo** profile is retained for comparison
with the 2026-10-15 benchmark. It is separate from the nominal 30 Hz JPEG
workflow. From `musohu_ws`, after sourcing the workspace:

```bash
ros2 launch helmet_bringup helmet_sensors.launch.py \
  zed_params_file:="$(ros2 pkg prefix helmet_bringup)/share/helmet_bringup/config/zed_stereo_no_depth.yaml"
# In another sourced terminal:
./scripts/record-evaluation.sh --label stereo_no_depth \
  --topics src/helmet_bringup/config/recording_stereo_no_depth.yaml
```

This records `/zed2i/zed_node/{left,right}/color/rect/{image,camera_info}`
alongside the other sensors and VIO, at a requested 15 Hz image rate. The
`/rgb/` alias is the left image and is omitted to avoid duplication. Camera
calibration is retained for offline stereo processing. Disabling dense depth
does not disable GEN_3's own visual/inertial computation. See the measured
[power comparison](POWER_BENCHMARK.md). Web topic selection alone does not
change camera acquisition parameters; launch this profile before selecting
its topics in the web recorder.

## Sensor rate health

Combined bringup starts `musohu_sensor_health`; disable it explicitly with
`launch_health_monitor:=false` if another monitor is already running. It counts
`/witmotion_imu/imu` at 200 Hz, `/zed2i/zed_node/odom` at 30 Hz and
`/audio_stamped` at 15.625 messages/s. Audio is 16 kHz mono PCM16 in
1,024-sample chunks, about 2 KB per message; VAD/DOA are event-driven and
`/audio_info` is latched, so none provides a suitable capture-rate signal.
LiDAR point-cloud rate is intentionally skipped. Disabled launch sensors
are marked disabled, not missing.

Settings are in `config/sensor_health.yaml`: a 10-second rolling receive-rate
window, 5-second warmup, 2-second missing-data timeout and 1 Hz reports.
Within ±10% is healthy, with a ±5% target and a caution note between those
bounds. Both slow and unexpectedly fast streams are flagged outside ±10%.
Rates use monotonic receive time, independent of UTC adjustments. Summaries
publish on `/diagnostics` and atomically to
`~/.local/state/musohu/sensor_health.json`; `MUSOHU_HEALTH_FILE` overrides the
path. The web UI polls once per second and rejects snapshots older than four
seconds, from another boot or another ROS domain. No image/cloud subscriptions
are created by this monitor. These checks establish stream throughput, not
image recording rate, tracking accuracy, synchronization or calibration.

## Evaluation recording and hardware checks

```bash
./scripts/record-evaluation.sh --label urban_loop_01
# Stop with Ctrl-C, then inspect the completed bag:
ros2 bag info ~/helmet_bags/<bag-name>
```

The helper records the manifest in `src/helmet_bringup/config/recording_topics.yaml`
and writes adjacent request metadata containing repository/submodule versions
and SDK state. Supply `--topics` and `--output` to change the manifest/output.
This command-line helper retains its lightweight request metadata. For recorder-
confirmed state, editable topic presets and complete final session metadata,
use the [web recording workflow](../web-app/README.md).

Verify `/rslidar_points`, `/witmotion_imu/imu`, `/zed2i/zed_node/imu/data`,
`/zed2i/zed_node/imu/data_raw`, `/zed2i/zed_node/odom`, `/zed2i/zed_node/pose`,
`/tf`, `/tf_static` and `/diagnostics`. Check topic types, rates, frame IDs,
timestamps and effective GEN_3 parameters. Check PointCloud2 fields for
per-point time/ring before selecting LIO; the fork now defaults to XYZIRT and
publishes `ring` and absolute `timestamp` fields. LiDAR now uses its native
PTP-disciplined clock; [clock setup and startup checks](TIME_SYNC.md) are required. Polling/publication configuration is not a measured sensor rate.

Keep calibration, clock synchronization and route conditions constant between
IMU comparisons. Verify recording message counts and playback before using a
bag for drift comparisons. Observe the running rig with the bounded probe:

```bash
python3 ./scripts/validate-sensors.py --duration 30 --output /tmp/rig-check.json
# Isolate sensors when diagnosing a failure:
python3 ./scripts/validate-sensors.py --sensors imu lidar audio --duration 20 \
  --output /tmp/noncamera-check.json
```

The probe reports observed rates, timestamps, acceleration, PCM audio, image
layout, LiDAR point fields and diagnostic statuses. It refuses to overwrite
reports and exits nonzero for missing streams or nonincreasing timestamps.
This short acquisition check does not validate calibration or trajectory drift.
This checkout's web app targets the new workspace. The existing deployed
service still uses its separate old checkout; deployment preparation does not
replace it. New full recordings use `/audio_stamped` and `/audio_info`; legacy
headerless `/audio` remains available for existing callers.

For the observed USB protocol failure, `./scripts/recover-zed-usb.sh --check`
identifies the ZED video device's parent USB 3 hub. With sensors stopped,
`--reset` uses sudo to rebind that hub and refuses if other USB devices are
present beneath it. This is a recovery attempt; it does not diagnose the root
cause or reboot the host. Preserve the kernel log and compare against
[Stereolabs USB troubleshooting](https://support.stereolabs.com/articles/2190934729-how-to-fix-usb-3-0-bandwidth-and-connection-issues)
if video still does not enumerate.

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
the default ZED namespace. No unverified camera-to-LiDAR/IMU extrinsics are
published. Measure those against the final helmet CAD before starting LIO.
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
faster tracking option. HD720 capture is 30 Hz; image/depth publication is
15 Hz and unsynchronized IMU publication is requested at 200 Hz. These are
starting settings to benchmark, not measured performance guarantees.
[Tracking modes](https://docs.stereolabs.com/docs/development/zed-sdk/modules/positional-tracking/modes),
[ROS tracking parameters](https://docs.stereolabs.com/docs/integrations/ros-2/positional-tracking).

Odometry is kept continuous across loop closures; corrected poses use `map`.
When integrating another estimator, disable ZED TF publication as appropriate
with `publish_tf:=false publish_map_tf:=false` in the individual ZED launch.
Do not create two publishers for the same TF edge.

Neural depth defaults to `NEURAL_LIGHT` for the Nano's compute budget; this is
independent of choosing the newest tracking algorithm. Point cloud, mapping,
body and object detection are disabled to reserve resources for recording/LIO.
Increase depth quality only after measuring sustained frame rate and memory.

For **rectified left/right colour without dense depth**, use the paired
capture profile and recording manifest below (commands from `musohu_ws`,
after sourcing the workspace). GEN_3 VIO and ZED IMUs remain enabled.

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

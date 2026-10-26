# MuSoHu ROS 2 workspace

ROS 2 Humble on Jetson Orin Nano: ZED 2i / SDK 5.5, Helios H32F70,
WT901 and ReSpeaker. `helmet_bringup` owns integration; the native
`musohu_bag_recorder` serves the [web app](../web-app/README.md) and CLI.
Commands below run from the repository root. Research work is in [TODO.md](../TODO.md).

## Setup and build

Ubuntu 22.04, JetPack/L4T 36.4 and the ROS 2 Humble apt repository are prerequisites.
The setup helper installs dependencies, SDK 5.5, device rules and the local Zenoh
router service, then builds sequentially with `--symlink-install`:

```bash
git submodule update --init --recursive
./musohu_ws/scripts/setup.sh
# Separate dependency installation or rebuilding:
./musohu_ws/scripts/setup.sh --deps-only
./musohu_ws/scripts/setup.sh --build-only
```

Drivers are pinned RobotiXX submodules on `musohu-v2`: ZED derives from `main`,
WitMotion from `robotixx-ros2-humble`, plus audio_common, respeaker_ros,
rslidar_msg and rslidar_sdk (including nested rs_driver). Initialize recursively;
do not update gitlinks during ordinary setup. `zed_description` is the native
`ros-humble-zed-description` dependency. `nlohmann-json3-dev` provides the ZED
wrapper's C++ JSON headers. Keep `~/ros2_musohu_ws` as a reference checkout only.

For a manual build, use a fresh shell with only the Humble underlay:

```bash
source /opt/ros/humble/setup.bash
cd musohu_ws
MAKEFLAGS='-j1 -l1' CMAKE_BUILD_PARALLEL_LEVEL=1 colcon build --base-paths src \
  --symlink-install --executor sequential --cmake-args -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=OFF -DBUILD_EXAMPLES=OFF -DBUILD_DOCS=OFF
```

## Nominal middleware: Zenoh

```bash
source /opt/ros/humble/setup.bash
source musohu_ws/install/setup.bash
./musohu_ws/scripts/zenoh.sh --check
ros2 launch helmet_bringup helmet_sensors.launch.py
```

Sourcing selects `rmw_zenoh_cpp` and localhost-only ROS communication. Setup
installs `musohu-zenoh.service`; `zenoh.sh --router` is a foreground alternative
when that service is stopped. Peers/router use loopback, SHM, a 32 MiB pool,
a 1 s congestion timeout and disabled multicast. Browser HTTP and native
LiDAR UDP/PTP remain available. Web control RPCs use loopback TCP to avoid a
Humble SHM response issue; sensor/recorder bulk data retain SHM.

In short stationary trials, tuned Zenoh reduced recorder CPU about **34%** and
system CPU **5 percentage points**, averaging **28.08 versus 26.55 saved stereo
pairs/s** with asynchronous Fast DDS. The median gap was smaller (28.60 versus
28.25); shared-memory mappings increased reported RSS. These are observations,
not a sustained 30 Hz guarantee. RELIABLE KEEP_LAST and ZED C++ IPC stay enabled.

### Use Fast DDS if needed

Stop recording and sensors first. All communicating nodes/CLI tools need the
same middleware and ROS domain; stop/relaunch them when switching:

```bash
ros2 daemon stop
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export RMW_FASTRTPS_PUBLICATION_MODE=ASYNCHRONOUS
source musohu_ws/install/setup.bash
ros2 launch helmet_bringup helmet_sensors.launch.py
```

For the deployed web app, a terminal export is insufficient. With hardware
stopped, use `sudo systemctl edit musohu-web.service` and add:

```ini
[Service]
Environment="RMW_IMPLEMENTATION=rmw_fastrtps_cpp"
Environment="RMW_FASTRTPS_PUBLICATION_MODE=ASYNCHRONOUS"
```

Then run `sudo systemctl daemon-reload` and `sudo systemctl restart musohu-web.service`.
To return to nominal, set that override and terminal `RMW_IMPLEMENTATION` to
`rmw_zenoh_cpp`, source the workspace and relaunch. Keep other service overrides.

### Read a Zenoh recording with DDS

ROS bags contain CDR messages, not a middleware-specific payload format.
Humble Zenoh records `avoid_ros_namespace_conventions: true` in offered QoS;
Fast DDS playback needs that flag false. Make a verified copy:

```bash
source /opt/ros/humble/setup.bash
source musohu_ws/install/setup.bash
python3 musohu_ws/scripts/convert-bag-for-dds.py /path/to/source_bag /path/to/new_dds_bag
RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1 \
  ros2 bag play /path/to/new_dds_bag
```

The helper normalizes every topic's naming flag, preserving types, other QoS
(including transient-local), serialized bytes and receipt timestamps. It verifies
the copy and saves `dds_conversion.json`; the original is untouched. Output is
**uncompressed MCAP**, so allow sufficient space even for a compressed input.
Play separately from live hardware. No Zenoh router or sensors are needed to convert.

## Sensors and stereo recording

Default: **15 W**, SDK depth **NONE**, GEN_3 **PREFER_GPU**, capture/compute/publish
**60/30/30**, packed unrectified **BGR8 uncompressed**, **1280×720 per eye**.
Both ZED IMUs run independently near 200 Hz (`sensors_image_sync: false`).
Retain both camera calibrations and all IMU streams for offline depth/LIO.

The Full rig manifest records `/zed2i/zed_node/stereo/color/raw/image`
(`sensor_msgs/Image`, 2560×720). Split columns 0–1279 / 1280–2559 into left/right;
both halves have one acquisition stamp. Use the respective optical frames and
`left/color/raw/camera_info` / `right/color/raw/camera_info` under the same node.
Packing keeps each pair together; it neither halves pixel bytes nor prevents
whole-frame drops. The Separate RGB preset remains available.

The initial BGR8 comparison saved **26.50 pairs/s** packed/unrectified/uncompressed
versus **16.20** separate/rectified/JPEG95; several settings changed together.
Later nominal recordings reached about **28.5**. BGR8 carries 25% fewer bytes
than BGRA8. PREFER_GPU averaged about 7% more saved pairs and 11% less ZED CPU
than PREFER_CPU, using more GPU; 25 W provided no consistent throughput benefit.
Assess saved images after excluding startup; odometry health is not an image-rate check.

| Configuration | File under `src/helmet_bringup/config/` |
| --- | --- |
| Camera/tracking | `zed_params.yaml` |
| WT901, 115200 baud / approximately 200 Hz | `imu_params.yaml` |
| LiDAR, native XYZIRT point time/ring | `lidar_params.yaml` |
| Final measured transforms | `sensor_extrinsics.yaml` |
| Recording topics | `recording_multimodal.yaml`, `recording_multimodal_separate.yaml`, `recording_topics.yaml` |
| Lightweight rate health | `sensor_health.yaml` |

Individual launches: `zed.launch.py`, `imu.launch.py`, `lidar.launch.py`,
`audio.launch.py` in `helmet_bringup`. Combined launch supports
`launch_zed`, `launch_imu`, `launch_lidar`, `launch_audio`, `launch_static_tf`
and `launch_recorder` switches. Final current-rig extrinsics are accepted;
use one TF publisher per edge. WT901 uses Qt port name `witImu`.
ReSpeaker and WT901 settings/calibration are accepted; preserve them.

ZED `odom` is continuous local pose plus velocity/covariance in `odom`;
`pose` is camera pose in `map`, corrected by loop closure. Record both.
Fused `imu/data` includes orientation/calibrated measurements; `imu/data_raw`
contains uncalibrated acceleration/gyro. Dense depth stays disabled.

## Session clocks

With sensors and recording stopped, open **http://10.42.0.1:8000/** on the
hotspot (or the Jetson LAN address). Offline, use **Sync from this phone**;
online, use **Use internet time** and wait for a ready reference. After each
battery swap/reboot, synchronize again before starting hardware. Never step
the host clock during sensor operation or recording.

Phone UTC or NTP owns Jetson system time. `musohu-ptp.service` serves it over
`eno1` using software UDPv4/E2E PTP, domain 0; there is no PHC or phc2sys.
Jetson `192.168.1.102/24`, Helios `192.168.1.200`, LiDAR `PTP-E2E-L4`.
Phone sync disables NTP, checks native LiDAR epoch and stores a boot-scoped
reference (24 h expiry). PTP reads the adjusted system clock without a restart.
Startup fails closed without a ready reference; `/diagnostics` monitors clock state.

```bash
./musohu_ws/scripts/ptp.sh --install --interface eno1  # provisioning, uses sudo
./musohu_ws/scripts/ptp.sh --status --interface eno1
python3 musohu_ws/scripts/lidar-time.py
```

LiDAR uses native PTP acquisition time; ZED uses the SDK's host-clock mapping;
WT901 uses host receive time. `/audio_stamped` maps PortAudio ADC time to host
UTC with a receive-time fallback. These USB sensors are not hardware PTP endpoints.

## Recording and archival

Use the web Full rig preset, or launch the stack and record through its native service:

```bash
./musohu_ws/scripts/record-evaluation.sh --label urban_loop_01
# Ctrl-C finalizes; --duration 30 stops after confirmed recording.
ros2 bag info ~/helmet_bags/<session>
```

The CLI defaults to the odometry-evaluation manifest; pass
`--topics musohu_ws/src/helmet_bringup/config/recording_multimodal.yaml` for Full rig.
Canonical writer settings are in
`src/musohu_bag_recorder/config/bag_recorder_config.yml` (also linked from the web app):
**MCAP, no compression, 500 MB per cache buffer**. MCAP reduced recorder CPU
about 15% versus SQLite3 in the fresh-launch comparison; file-size overhead was similar.
Automatic Zstd rewriting is **disabled**. Opt in per new session with
`ros.mcap_postprocess.enabled: true` in `web-app/config.yml`; no restart is needed.
When enabled, verified rewriting finishes before the next recording can start.

Approximate whole-bag storage, from a 120.33 s stationary recording without
ReSpeaker (decimal GB; scene, topic selection and saved rate affect size):

| Representation | GB per recorded minute | Image fidelity |
| --- | ---: | --- |
| Raw BGR8 / uncompressed MCAP | 10.38 | Original |
| Raw BGR8 + internal Zstd | 7.13 | Lossless |
| PNG rewrite + internal Zstd | 5.10 | Pixel-identical |
| JPEG95 / 4:2:0 rewrite + internal Zstd | 1.58 | Lossy; depth accuracy unvalidated |

PNG/JPEG figures are retained archival estimates; image-rewrite experiment
scripts were retired. Original bags and external experiment artifacts are preserved.

## Health and troubleshooting

The 1 Hz web health panel checks lightweight WT901/ZED odom/audio rates with
10 s windows, 5 s warmup, a ±5% target and ±10% healthy limit. It does not
subscribe to images/clouds or validate tracking accuracy. Settings live in
`sensor_health.yaml`; snapshots are in `~/.local/state/musohu/sensor_health.json`.

```bash
python3 musohu_ws/scripts/validate-sensors.py --duration 30 --output /tmp/rig-check.json
./musohu_ws/scripts/recover-zed-usb.sh --check
```

The first checks bounded sensor samples; USB recovery `--reset` requires stopped
sensors and sudo, and refuses a hub shared with unrelated devices. For recorder
services and dummy development, see the [native recorder](src/musohu_bag_recorder/README.md)
and [web app](../web-app/README.md). No hardware benchmark or clock retuning is
part of ordinary setup.

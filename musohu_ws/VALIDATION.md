# Validation record

## 2026-10-21: finalized sensor extrinsics

The maintainer confirmed commit `2c33979` contains the accurate, final sensor
extrinsics for the current rig. `config/sensor_extrinsics.yaml` in
`helmet_bringup` is the canonical source for `zed2i_camera_link → rslidar`
and `zed2i_camera_link → imu_link`. The to-do list marks this work complete;
bringup and LIO integration should reuse these values. Numerical transforms
and frame definitions are unchanged by this status/documentation update.

## 2026-10-21: nominal JPEG stereo and web sensor-rate health

Reviewed the maintainer's HD720/30 Hz, GEN_3/PREFER_GPU, depth NONE and 24-bit
BGR settings against pinned wrapper source. The nominal Full rig manifest
now records left/right `/color/rect/image/compressed` JPEG topics plus both
classic CameraInfo topics, calibrated/raw ZED IMUs, odometry and map pose;
the old RGB/depth requests were removed. The maintainer chose independent
~200 Hz ZED IMUs: `sensors_image_sync` is false. A probe with the former true
setting received no IMU messages without image subscribers. Source confirms
that mode uses image-referenced sensor data; it is not a full-rate IMU mode.
Runtime checks confirm NONE, GEN_3, BGR24, sync false, both IMU publishers
enabled and no dense-depth image publisher. The installed JPEG plugin reported
quality 95 on both cameras, saved in session metadata. Future sessions also
capture the BGR24 and sensor-sync settings explicitly.

Added `musohu_sensor_health` to combined bringup with selectable launch flag
and per-sensor enabled states. It subscribes only to WitMotion IMU, ZED odom
and small stamped audio chunks, targeting 200, 30 and 15.625 messages/s.
Reports use monotonic receive time over 10 seconds, 5-second startup warmup,
2-second missing-data timeout and 1 Hz output. ±10% is healthy; ±5% is the
target. The web reads atomic snapshots, rejects stale/wrong-boot/wrong-domain
data and shows LiDAR as not monitored. ROS `/diagnostics` retains the reports
in bags. Health is receive throughput only, not image/timestamp/pose accuracy.

The previous manual sensor launch was running without a recorder. Stopped it
cleanly and restarted through the new preview web app on port 8001, so the UI
now owns sensor start/stop. ReSpeaker was absent initially; the maintainer
reconnected it and all three monitored streams became healthy. Existing
recordings and the older service on 8000 were preserved. ROS stays local-only;
no host clock, PTP, power-mode or network changes were made.

The full 18-topic recording finalized with **72,281 messages** over **80.12 s**:
WitMotion ~200.51 Hz; calibrated/raw ZED IMUs ~199.99 Hz each; odom and map pose
~29.44 Hz; stamped audio ~15.62 Hz. All 2,362 ZED tracking-status samples were
OK. The bag contains 1,331 images per camera, **all exactly paired by header
stamp**, at ~16.64 Hz each. Sampled JPEGs decoded to 1280×720 BGR colour;
camera calibrations were present. Odometry frames were `odom`, pose frames
were `map`. Bag size was 1.855 GB. No selected topic was empty. The test
harness initially used GET for stop and received 405; corrected to POST and
finalized the same recording through the API, preserving all captured data.

Important limits: two repeated header stamps occurred in each odom/pose
stream, with no backwards steps there; each CameraInfo stream had one
backwards transition. A later live probe again flagged odom/pose duplicates
and CameraInfo transitions. These are recorded follow-ups, not a passed
timestamp-consistency result. JPEG image stamps were strictly increasing.
Both-stream JPEG reception without recording stayed ~16.1 Hz; left alone
reached ~27.4 Hz. A runtime quality change to 80 was accepted but barely
changed encoded sizes, so it is not a validated quality/performance sweep.
Quality parameters were restored to 95. Do not promise 30 Hz saved images
from the 30 Hz setting or from healthy odometry alone. No power, calibration,
drift or long-route accuracy result is implied by this pilot.

Validation passed: five rate-window unit tests, three snapshot-expiry tests,
one real-ROS monitor test covering healthy→slow→missing and diagnostics,
nine existing real-ROS recording tests and the expanded metadata regression.
The ROS integration fixture initially used a separate context with the global
executor; corrected the fixture and reran successfully. Browser checks covered
compressed topic defaults, healthy/offline rendering, three real healthy
cards, LiDAR skipped and desktop/mobile layout without page errors. Isolated
domain-108 bag playback delivered both JPEGs, both ZED IMUs, odom and pose.
Sequential symlink build, YAML/Python, package discovery and launch argument
checks passed. Historical depth benchmark config/manifests were separated
from nominal acquisition to preserve the benchmark's intended workload.

Evidence is in ignored `musohu_ws/log/stereo-health-2026-10-21/`; the bag is
under `~/helmet_bags/stereo_compressed_health_20261021_20261021T202907_543dc14e`.
Session metadata records source SHAs, config contents/hashes, effective
parameters and NTP reference. The new preview and sensor launch remain
running for the maintainer, with the test recorder stopped.

## 2026-10-21: localhost-only ROS communication

Configured `ROS_LOCALHOST_ONLY=1` through the `helmet_bringup` workspace
environment hook, web ROS command wrapper and systemd template. The current
user's `~/.bashrc` sets it before the noninteractive early return; its previous
contents were saved under `~/.local/state/musohu/`. Stopped the existing domain
0/96 ROS CLI discovery daemons and restarted the idle new web preview on 8001
with the setting. The older deployed 8000 service was not migrated.

Sequential symlink build of `helmet_bringup`, Python/shell syntax checks,
package discovery and combined-launch argument checks passed. Fresh-shell
workspace sourcing and explicit `.bashrc` sourcing both changed an inherited
`ROS_LOCALHOST_ONLY=0` to 1. The web command wrapper did the same. The real-ROS
dummy recording start/flush/restart regression passed twice within its test,
including saved `ros_localhost_only: "1"` metadata. The preview returned HTTP
200, remained bound to `0.0.0.0:8001`, and its environment was checked directly.
The dedicated software PTP service remained active/running. This change
restricts ROS DDS; native LiDAR UDP/PTP and browser HTTP remain separate.
No full hardware launch or second-machine visibility test was performed.
Local logs are in `musohu_ws/log/localhost-2026-10-21/`.

## 2026-10-21: WT901 after external calibration/rate change

The maintainer reports calibrating the sensor externally and selecting
230400 baud/200 Hz. The edited YAML contained 230400 and 5 ms polling, but
the launch file still overrode baud with a hard-coded 115200. Its default
now reads the YAML baud rate; explicit `baud:=...` overrides remain supported.

A launch explicitly using 230400 opened the port but produced no IMU or native
quaternion messages. A passive raw-serial check found 36,800 undecodable bytes
at 230400 over three seconds, then 602 valid packets of **each** acceleration,
gyro, Euler-angle and magnetometer type at 115200 over three seconds. No sensor
configuration/calibration/time commands were sent. With the maintainer's
approval, the YAML baud is now 115200, retaining 5 ms polling. Do not claim
230400 is active on the sensor; it must be reapplied/saved and reverified if
needed later. Polling does not set the sensor's output frequency.

At verified 115200, the 60-second live probe measured 200.48 Hz without issues.
The approximately 64-second finalized bag contains 12,813 `sensor_msgs/Imu`
messages in `imu_link`, header rate 200.51 Hz, all values finite, no duplicate
or backward stamps, and quaternion norms 1 within floating-point precision.
Mean acceleration magnitude was 9.809 m/s², mean gyro components approximately
[0.000025, 0.000035, -0.000017] rad/s. These readout checks do not independently
prove calibration accuracy, axis conventions or dynamic response. Median
header interval was 4.89 ms, p99 10.67 ms, maximum 12.38 ms: host serial/poll
buffering remains visible. Median bag-receive minus header time was 0.30 ms;
this is ROS delivery delay, **not** sensor acquisition latency or synchronization
error relative to LiDAR.

A separate ten-second passive capture found 2,005 packets of each of the four
types, zero checksum failures and no discarded nonheader bytes. No RTC (`0x50`)
or native quaternion (`0x59`) packets appeared. The separate headerless
`/witmotion_imu/orientation` topic was advertised but recorded zero messages;
the IMU orientation is Euler-derived despite native preference being enabled.
Source inspection also confirms the existing driver does not clear its Euler
freshness flag after publishing, allowing previous-cycle angles with current
acceleration/gyro. This remains an explicit pre-LIO follow-up, not a validated
orientation/acquisition synchronization guarantee.

Playback in isolated domain 97 delivered 838 IMU messages and stopped cleanly.
Hardware checks used domain 96. Python/YAML checks, package discovery, sequential
symlink build of `helmet_bringup` and `imu.launch.py --show-args` passed. A final
launch without baud overrides confirms the corrected config/default path.
No firmware, calibration, Jetson time, PTP or running web-service settings were
changed. NTP is currently off and the stored host reference is not ready;
these checks establish relative timestamp continuity, not absolute UTC accuracy.
Sync phone/NTP before the next guarded full-stack session.

RTC remains disabled, with `presync: false` explicit. Its publisher only exposes
sensor calendar packets; it never changes IMU header stamps or disciplines
the host/LiDAR. See [TIME_SYNC.md](TIME_SYNC.md) for implementation details and
serial bandwidth implications. Evidence, raw capture, finalized bags, effective
parameters, driver/library SHAs and playback result are ignored local artifacts
under `musohu_ws/log/imu-validation-2026-10-21/`.

## 2026-10-15: stereo colour recording without dense depth

Added opt-in `zed_stereo_no_depth.yaml` and `recording_stereo_no_depth.yaml`.
Rebuilt `zed_components` and `helmet_bringup` sequentially with symlink install;
Python/YAML, package discovery and combined-launch argument checks passed.
ZED fork commit `8d68173` (published on RobotiXX `musohu-v2`) moves tracking
parameter initialization ahead of the depthless GEN_3 gate. A regression
launch with an unavailable camera serial verifies NONE + GEN_3 parsing without
opening hardware; it passed. Before the fix, the same hardware configuration
published images but no odometry/status.

Live publisher/parameter checks after the fix confirm NONE, GEN_3 enabled,
SYSTEM_CLOCK, left/right colour enabled, RGB alias disabled, no depth-map
publisher, and active odometry/status publishers. Full-rig recording finalized
cleanly with 37,574 messages across all 18 selected topics. The 25 W pilot
measured VDD_IN 8.65 W mean/9.05 W p95, CPU/GPU maximum 54.9 C, and all 1,658
tracking statuses OK. LiDAR diagnostics stayed PTP Locked with phone time as
the accepted offline reference. No backward stamps were found in images,
odometry, cloud or stamped audio.

Stereo audit: 890 left/893 right HD720 BGRA8 frames; 888 exact-stamp pairs.
Some missing counterparts occurred inside the recording. Both CameraInfo
streams had one out-of-order arrival near startup, and a few images lacked
an exact recorded calibration stamp. Calibration matrices were retained.
Do not report lossless stereo or measured outdoor drift. See
[POWER_BENCHMARK.md](POWER_BENCHMARK.md) for rates, storage, scope and evidence.

The first run exposed another depthless-specific issue: requesting the
undeclared depth-stabilization parameter made Humble's GetParameters response
empty. The web recorder now lists declared names before querying, records
available effective settings, and marks undeclared names explicitly. A live
repeat verifies NONE/GEN_3/PREFER_GPU and stereo publication in session metadata.
That repeat measured 8.62 W mean/8.85 W p95; all 1,582 tracking statuses were
OK, with 860 exact pairs from 862 left/864 right images. Pairing/calibration
gaps recurred. The new real-ROS recording regression test, using a synthetic
ZED node with undeclared depth-stabilization settings, passed after correcting
the fixture's publisher namespace. Both hardware launches and recorders
stopped cleanly; the host remains in 25 W mode.

## 2026-10-15: offline clock integration and depth power pilot

The phone UTC feature existed in the deployed older checkout, not this
checkout. The new app now supports phone UTC epoch milliseconds offline,
explicit NTP disabling, guarded clock changes while all acquisition is stopped,
and post-change verification of LiDAR lock plus native MSOP packet epoch.
A phone reference is boot-scoped, expires after 24 hours or an unexpected
wall-clock step, and is recorded with session metadata. Runtime diagnostics
accept this reference without requiring internet NTP. The deployment template
permits narrowly allowed clock commands and installation provisions their
sudoers file; the existing deployed service remains unchanged.

- Seven clock workflow/reference tests and eight real ROS recording tests pass.
- Four native LiDAR clock tests pass, including refusal when host time starts
  near the Unix epoch. Package build, syntax and launch argument checks pass.
- A mobile browser displayed the clock card and rejected a sync request while
  an external full-stack benchmark was active, without executing a clock step.
- Live simulated-phone requests stepped the host forward two seconds and
  restored its original clock progression with NTP disabled. Both returned
  HTTP 200 after native LiDAR lock/packet epoch checks, in about 4.0 and 5.2 s.
  Packet delivery-age ranges were 7.36–9.14 ms and 7.40–10.53 ms. Software PTP
  stayed active without restarting it; no independent eno1 clock was set.
- A subsequent 18-topic offline recording finalized 6,342 messages. Both start
  and stop metadata identify the phone reference; recorded clock diagnostics
  were OK with host_reference=phone, NTP synchronization=no and LiDAR Locked.
  Effective ZED parameters were read through a single parameter RPC and confirm
  NEURAL_LIGHT, GEN_3, PREFER_GPU, SYSTEM_CLOCK and the intended publication
  rates. The full rig then stopped with exit zero.
- Reboot invalidation and a Unix-epoch host are covered by tests; this session
  did not deliberately reboot or set the host all the way back to 1970.

Power measurements use INA3221 VDD_IN: **Jetson total module power**, not
whole-battery/helmet power. At the unchanged nvpmodel 25 W setting, one-minute
full-stack 18-topic recording intervals measured NEURAL_LIGHT mean 10.93 W
(p95 12.02 W) and NEURAL mean 16.01 W (p95 16.57 W); idle wired hardware with
drivers stopped averaged 6.34 W. Depth retained about 14.5 / 14.7 Hz and
odometry 26.7 / 26.3 Hz respectively. All sampled odometry status values were
OK, but NEURAL logged two failures to allocate a tracking keyframe. Scene
finite-depth fractions were 39.0% / 42.7%, not depth-accuracy measurements.
NEURAL required first-use engine optimization, excluded from recording power.
NEURAL_PLUS did not finish first-use optimization within the 15-minute
startup bound. It logged CUDA allocation warnings and remained at 90.1%; the
launch escalated its stuck shutdown to SIGKILL. No PLUS recording watts or
frame rates were measured, and this is not proof that cached-engine inference
cannot run. The following NEURAL_LIGHT offline acquisition recovered cleanly.
A cached-engine NEURAL repeat finalized 38,226 messages at mean 16.47 W,
p95 16.92 W, depth 14.65 Hz and odometry 26.67 Hz. All 1,670 status samples
were OK and the two first-optimization keyframe errors did not recur. This
avoids treating retained optimizer memory as normal cached-engine behavior.
The final power comparison uses that repeat; the original run is preserved.

The host had NTP disabled on arrival (kernel NTPSynchronized still reported
yes). These initial power runs preserve that existing host clock, check PTP
packet epoch against it, and make no absolute UTC accuracy claim. The new
phone reference workflow separately addresses this offline case.

Live clock evidence is `clock-live-test.json`, `offline-full-rig.json` and
`offline-clock-diagnostics.json` under the same directory below. The caller
emulated phone epochs; physical phone UTC accuracy and a complete battery
power cycle were not measured.

Raw generated evidence is under `musohu_ws/log/depth-power-2026-10-15/`, with
benchmark data in `25W-v3/`; the first two sampler-only attempts were corrected
before launching sensors. See [POWER_BENCHMARK.md](POWER_BENCHMARK.md) for
method, limits, reproduction commands and final comparison results.

## 2026-10-14 after reboot: full rig, PTP and web recording

This supersedes the ZED recovery blocker in the earlier same-day record below.
After the maintainer rebooted, ZED USB 3 video enumerated and SDK 5.5 opened
successfully. Three camera/full-stack launches exited cleanly across testing;
no repeat camera crash was observed in these short runs. The underlying cause
of the earlier USB failure has not been established.

The ReSpeaker pin is now `a24cf21d7d7daff80d36e6167bf1114dc6e15214`, published
on RobotiXX `musohu-v2`; other pins remain as recorded below. The change adds
standard stamped PCM audio with PortAudio ADC-to-host mapping and audio format
metadata while preserving legacy raw topics. Its four focused tests pass.
`helmet_bringup` rebuilt with `--symlink-install`; its three clock-guard tests
pass. Python/YAML, package discovery and launch argument checks also pass.

### Acquisition and clocks

Validation used only Humble and this workspace on isolated ROS domain 96.
Effective startup settings include SDK 5.5, GEN_3, PREFER_GPU, IMU fusion,
gravity alignment, area memory and full 3D motion. ZED initially waited for
gravity alignment, then reported odometry OK. A 30-second full-rig observation
reported no missing streams or backward header timestamps in the sampled
images, IMUs, clouds, audio and trajectories:

| Stream | Observed rate | Qualification |
| --- | --- | --- |
| WT901 | 10.00 Hz | Sensor output remains too slow for many LIO configurations; firmware/freshness audit pending |
| Helios | 10.01 Hz | XYZIRT, 32 rings; native PTP-disciplined point timestamps |
| Audio raw/stamped | 15.63 chunks/s | 2,048-byte mono PCM16 chunks, 16 kHz; median stamped delivery age 67.8 ms |
| ZED IMU / raw IMU | 194.6 / 194.3 Hz | Host clock mapping, not PTP hardware capture |
| ZED odometry / pose / status | about 29 Hz | All 848 sampled odometry status values were OK (0) |
| ZED RGB / depth | 6.94 / 6.72 Hz at best-effort probe | Probe drops under load; final bag retained about 15 Hz over its short span |

Only the camera's own TF tree was present, with one parent per child. External
sensor geometry is not measured, so no guessed static transforms were added.
No route, loop drift, covariance, extrinsic or sustained thermal validation was
performed. Brief tegrastats observations near shutdown showed about 4.7/7.6 GB
RAM plus 0.8 GB swap, CPU/GPU temperatures around 52–53 C; this is a snapshot,
not a steady-state performance result.

The maintainer installed `musohu-ptp.service` using the new helper. `eno1`
(`192.168.1.102`) exposes software timestamps only and has no PHC. Host
systemd-timesyncd remained synchronized over existing WiFi. No hotspot,
network address or host clock discipline was changed, and no phc2sys runs.
The PTP service was MASTER and Helios (`192.168.1.200`) read back
PTP-E2E-L4/domain 0 with **Locked** status. Existing network/RPM settings were
preserved. A stable eight-second sample contained 12,003 MSOP packets and
DIFOP sync mode/status 1/2. Host receive-minus-native-packet time was:

- minimum 7.35 ms, median 7.90 ms, p95 8.40 ms, maximum 17.54 ms;
- no UTC epoch or 37-second offset error observed;
- these include delivery delay and do not measure PTP synchronization accuracy.

Native LiDAR timestamps are enabled. The launch checks lock and actual packet
epoch before starting the driver; clock-health diagnostics reported OK, host
NTP synchronized, local PTP active and device Locked. Median cloud header age
was 122 ms because headers reference the first point of a full revolution;
maximum observed age was 494 ms under load. ZED's short camera-only IMU sample
had median header age around -6 ms, versus +6 ms during the full-rig sample;
SDK/host mapping and inter-sensor offsets still require calibration.
[Timestamp interpretation and operation](TIME_SYNC.md).

### Web, real recording and playback

This checkout's app now controls the new workspace with owned process groups,
editable presets and confirmed rosbag state. The original service on port
8000 in `~/git/MuSoHu` was preserved throughout testing. A temporary preview
used port 8001, separate ROS domains and ignored test output directories.

- Eight real-ROS API tests passed, including concurrent starts, invalid input,
  missing publishers, flushed bags/unique restart, cancellation during startup,
  restart during Stop cleanup, worker failure and successful bag finalization
  after the API was killed.
- A fresh Python venv (without system site packages) installed production
  requirements and recorded all four dummy topics, finalizing 84 messages.
  This validates Python provisioning on this host, not a clean OS install.
- Desktop browser test recorded all 16 selected hardware streams and finalized
  4,736 messages. Logs and Disk Space pages returned successfully.
- A 390-pixel mobile browser selected all three presets, recorded the full
  18-topic preset and confirmed finalization: **4,030 messages**, every selected
  topic nonempty, no JavaScript errors. A long output-path overflow was fixed.
- The full bag includes RGB/depth and camera calibration, LiDAR, both IMUs,
  GEN_3 trajectories/status, stamped audio/format/DOA/VAD, TF and diagnostics.
  Independent deserialization counted exactly the metadata totals. All 191
  recorded odometry status samples were OK; clock diagnostics were also OK.
- The audit found one backward header step (about 14.7 ms) on each CameraInfo
  topic near subscription startup. The pinned wrapper publishes host-now
  calibration messages without image subscribers and acquisition-stamped
  messages with images. This transition needs consideration by exact-time
  consumers; images, audio, IMUs, LiDAR and trajectories had no backward steps.
- Full bag playback on domain 98 and a separate acquisition probe both exited
  zero. Historical header ages during replay are not new live synchronization
  measurements. Audio data was separately deserialized and checked as PCM16.
- Every node in the final full-stack stop, including the camera container,
  time-sync monitor, ReSpeaker, WT901 and RoboSense, exited cleanly.
- Deployment preparation rendered and systemd-verified this checkout's service;
  installation/replacement of the old deployed service was not performed.

Raw evidence, screenshots and bags are local ignored artifacts under
`musohu_ws/log/validation-2026-10-14-reboot/`, including `full-ptp.json`,
`full-ptp-monitor.json`, `lidar-ptp-stable.json`, `web-ui-full-rig.json`,
`full-rig-bag-audit.json`, `full-rig-playback.json` and the regression logs.
Instructions: [web-app/README.md](../web-app/README.md). Longer recordings,
clock/power-cycle failure tests, WT901 settings/calibration and the outdoor
LIO/VIO experiments remain in [TODO.md](../TODO.md).

## 2026-10-14: individual forks and wired hardware

Sources now use individual RobotiXX submodules, all on `musohu-v2`:

| Driver | Pinned commit | Branch base |
| --- | --- | --- |
| audio_common | `d91fb78ef285c486303406ddfcbcf269e02ab7c4` | `ros2` |
| respeaker_ros | `10696ef` | `master`, already ROS 2 |
| rslidar_sdk | `1e801e36b3b099125bd4a23cfb0201084b5ef23a` | `main`, ROS 1/2 |
| rs_driver (nested) | `897b14d3bdb6186a75df27ba51b65b5bd5557723` | `main` |
| rslidar_msg | `fe8a95cb242bd294cc3d5e3422f2093fb49a56ee` | `master`, ROS 2 manifest |

ZED wrapper, description and WitMotion pins remain as recorded below. The
transitional legacy workspace submodule and source symlinks are removed.
`colcon list --base-paths src` now discovers 16 packages (adds sound_play_msgs).

- Nine replacement-driver packages built with `--symlink-install`; subsequent
  RoboSense/bringup/ReSpeaker rebuild passed after shutdown fixes.
- Native `nlohmann-json3-dev` is now installed. Build/buildtool/exec rosdep checks
  pass, excluding only `python3-spidev`, which setup provisions directly via apt.
- The maintainer completed `setup.sh --deps-only` successfully; the final
  `setup.sh --build-only` run built all 16 packages with `--symlink-install`
  against SDK `/usr/local/zed` and native JSON config `/usr/lib/cmake/nlohmann_json`.
- Setup helper help, invalid argument handling and shell syntax passed;
  Python/YAML checks and launch argument discovery passed.
- ReSpeaker regression checks pass for signed PCM16 sample round-trip,
  planar DOA quaternion convention, and audio cleanup before ROS shutdown.
- RoboSense SIGINT/SIGTERM regression passes without hardware on loopback UDP
  ports. Cleanup is idempotent and producer threads stop before ROS shutdown.
- ReSpeaker, WT901 and RoboSense all exited zero on the final non-camera
  hardware shutdown after the callback/context and driver cleanup fixes.

Wired acquisition used an isolated ROS domain (96), this workspace's overlay
and SDK 5.5, preserving the deployed web service. Short, mostly stationary
acquisition observed:

| Sensor | Observation | Limits |
| --- | --- | --- |
| WT901 | ~10.03 Hz; monotonic host timestamps, quaternion norm 1, acceleration magnitude near gravity | Firmware output rate is only ~10 Hz; no bias, orientation freshness or covariance calibration claim |
| Helios | ~10.01 Hz with reliable QoS; 57,600 points/cloud, rings 0–31, XYZIRT, ~0.1 s point timestamp span | Absolute host-derived timestamps; no PTP/extrinsic/LIO calibration |
| ReSpeaker | Six input channels recognized; main/channel PCM chunks 2,048 bytes at ~15.6 chunks/s = 16 kHz mono PCM16 | Headerless AudioData; acoustic direction and capture clock uncalibrated |
| ZED 2i | Enumerated at USB 3 / 5 Gbit/s; opened HD720/30; NEURAL_LIGHT optimization completed and cached | Camera reconnected, then container crashed (signal 11) during GEN_3 startup; no valid camera/tracking stream confirmed |

The initial best-effort LiDAR probe observed ~7–8 Hz while the reliable bag
retained 83 clouds in 8.27 seconds. Matching the driver's reliable cloud QoS
restored the probe to ~10 Hz. Configured rates are not substituted for measured
data; image/tracking rates remain unvalidated.

The recording helper finalized a 119.6 MiB SQLite bag on SIGINT (exit zero):
83 clouds, 84 WT901 messages, 121 main audio chunks, 121 channel-1 audio chunks,
5 DOA messages and 1 latched VAD message. Playback in separate domain 98 and
the acquisition probe both exited zero with valid IMU/cloud/PCM messages.
Session metadata preserves source pins. Raw logs/reports/bag are local generated
outputs; they are excluded from Git.

ZED recovery remains blocked after the maintainer's USB reconnects. Following
the crash, Linux initially listed stale video/HID devices, but the SDK device list was empty, reopening
times out with `CAMERA NOT DETECTED`, and a USB video reset returns
`Entity not found`. USB device permissions and video-node access were checked.
Kernel logs record repeated UVC/USB protocol failures (`-71`) and failure to
reset/disable the affected SuperSpeed port. Following reconnection, the HID
interface enumerated again, but no `/dev/video*` nodes returned and the SDK
still listed no camera. This does not establish whether the cause is SDK
recovery, cabling, power or hub behavior. Recover the USB 3 video path (including
host/hub reset if necessary) before repeating GEN_3, RGB/depth, IMU, TF and bag
checks. Do not report the full rig as validated yet.

The maintainer ran `recover-zed-usb.sh --reset` after its scope check confirmed
that USB 3 hub `2-1` had only the ZED video descendant. Unbind/rebind completed,
but the kernel then reported `can't set config #1, error -71` for the hub.
Bus 2 now has no enumerated hub/video children; USB 2 peripherals remain.
The SDK reports a ZED placeholder (`id=-1`, serial 0, `NOT AVAILABLE`) rather
than a usable camera. Further recovery needs a planned host/hub power cycle
or cable/power isolation. No host reboot was performed and all test sensor
processes were stopped; the original web service remains running.

Raw evidence and the test bag are retained locally under
`musohu_ws/log/validation-2026-10-14/` (ignored by Git).

## 2026-10-12 baseline

### Host and pinned sources

- Ubuntu 22.04.5, ROS 2 Humble, Jetson Orin Nano Super 8 GB.
- L4T 36.4.7 and CUDA 12.6 were retained.
- Installed ZED SDK upgraded from 5.1.0 to 5.5.0 through the official installer.
  The maintainer ran the helper in a normal terminal; agent sudo elevation is
  blocked by `NoNewPrivs`. The 5.1 backup was removed at the maintainer's request.
- SDK installer SHA256:
  `f59120ea95ea55fb2466515033b0823234410a5ccf2321af7960f0249f8c6884`.
  Installed `libsl_zed.so`, `libsl_ai.so` and `Camera.hpp` match the staged SDK.
- ZED wrapper: `b19902daf0136b6e841b5e415c2d01f425411c45`, RobotiXX `musohu-v2`.
- WitMotion: `91f1a39c77552ac2fb60525f35193355e8bf2c73`, RobotiXX `musohu-v2`.
- UART/Qt dependency: `5c2e86dd2ba7dba76d84e68fa7f65dc3527f5de0`.
- ZED description: `22468247c1653d08a1e213809f3e9ce76291487d`, upstream.
- Legacy driver source: `c627dd830ef21e3139d6c69dcbb1c5f61a3ff054`, RobotiXX
  `musohu-v2`; matches the committed Ashok reference checkout.

### Completed checks

- `colcon list --base-paths src`: 15 unique packages; no duplicate old bringup,
  standalone IMU or ZED wrapper.
- Full sequential build: all 15 packages passed using SDK 5.5 staged under
  `~/.cache/musohu/zed-sdk/extracted-5.5`. `nlohmann-json3-dev` was temporarily
  unpacked under `~/.cache/musohu/build-deps` because native installation needs
  a terminal with working sudo.
- After host installation, both ZED stereo and mono components rebuilt against
  `/usr/local/zed`; the camera shared library loads and resolves the installed
  SDK libraries successfully. The temporary JSON headers remain a build
  dependency until the native package is installed.
- ZED startup reports SDK 5.5.0 and confirms the project override file,
  GEN_3 tracking, GPU preference, IMU fusion, area memory, gravity alignment,
  full 3D motion and continuous odometry across loop closure. No parameter
  type errors occurred. Acquisition reported `CAMERA NOT DETECTED`, as expected
  without the camera; this does not validate tracking performance.
- Python AST, YAML parsing, shell syntax/help, and Git whitespace checks passed.
- Every project ZED override name matches the pinned common/model YAML schema.
- Combined and ZED launch argument discovery passed. Combined launch with all
  sensors disabled exits successfully. Legacy action executable is discoverable.
- WT901 launch exposes integer baud `115200`, topic `/witmotion_imu/imu` and
  frame `imu_link`, and stops cleanly.
- WT901 fork originally deadlocked/crashed at shutdown. Its fix removes recursive
  context shutdown, joins the executor thread and explicitly releases global
  publishers/services while ROS and Qt remain alive. The committed regression
  passes SIGINT/SIGTERM without hardware; three starts/stops with the helmet
  configuration also exit with code zero.
- Recording helper: dummy String topic recorded 11 messages; Ctrl-C finalized
  the SQLite rosbag; adjacent metadata contains repository/submodule versions;
  empty topic manifest rejected before creating an output directory.

### Remaining validation at that date

- Provision native `nlohmann-json3-dev` and confirm runtime/build rosdep checks.
- Camera and ReSpeaker were absent from USB inventory. Camera frames, depth,
  active GEN_3 tracking status, sensor rates and trajectory quality are not
  validated by compilation or launch discovery.
- WT901 serial port is present as `/dev/witImu`; measured sample rate, bias,
  covariance, timing and sensor quality still require recordings.
- LiDAR network/data, per-point times/rings, synchronization, measured static
  extrinsics and LIO comparisons remain in [../TODO.md](../TODO.md).
- The existing `~/ros2_musohu_ws` reference and running web service checkout
  were preserved. The web app still targets the old workspace pending migration.

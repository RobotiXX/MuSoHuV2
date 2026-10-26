# Web control and recording

FastAPI/Uvicorn controls this repository's `musohu_ws` and records selected ROS 2
streams with confirmed start/stop state. The app does not require a hotspot;
open the Jetson's current LAN address and the configured port.

This Jetson's production `musohu-web.service` now runs from this checkout on
port **8000**, with automatic startup at boot:

- On the helmet hotspot: **http://10.42.0.1:8000/**.
- On the current lab Wi-Fi: **http://192.168.0.129:8000/** (the LAN address can change).
- On the Jetson itself: **http://localhost:8000/**.

The HTTP listener binds to `0.0.0.0`, so changing between LAN and hotspot does
not require an app restart. ROS topics remain localhost-only. The saved
`Hotspot` profile uses `10.42.0.1/24`; the hotspot boot service also uses this
checkout. Starting it replaces the current Wi-Fi connection. Keep the working
LAN connection until you intend to switch to hotspot mode.

## Run this checkout

Build the ROS workspace first using [its setup helper](../musohu_ws/README.md).
Prepare the Python environment and a reviewable service file as your normal user:

```bash
./scripts/deploy/setup_production_web_service.sh --prepare-only
# From the repository root; choose a free port if the old service uses 8000:
web-app/venv/bin/python -m uvicorn app:app --app-dir web-app \
  --host 0.0.0.0 --port 8001 --workers 1
```

Use one Uvicorn worker; it owns the launched processes and session state.
Defaults in [config.yml](config.yml): workspace `../musohu_ws`, output
`~/helmet_bags`, full rig topic preset. `MUSOHU_WORKSPACE` and `MUSOHU_BAG_DIR`
override paths. ROS children source only Humble and this workspace and use
system Python, so the web environment need not contain ROS Python modules.
Process output goes to files under `web-app/logs`, not undrained pipes.

ROS children enforce `ROS_LOCALHOST_ONLY=1`, so sensor topics and recording
communication stay on the Jetson. The workspace environment hook and service
template apply the same policy. This does not restrict the HTTP listener:
phones/laptops can still use the web UI over Wi-Fi. Session metadata records
`ros_localhost_only` alongside `ros_domain_id` for auditing.

To install or update the production unit after reviewing the rendered file,
stop recording and sensors first, then run:

```bash
./scripts/deploy/setup_production_web_service.sh --install --port 8000
```

That command requests sudo to replace/restart `musohu-web.service`; it does
not configure a hotspot, DNS or firewall. See [deployment details](../scripts/deploy/README.md).
Use port 8001 only for a temporary preview; do not run two apps controlling
the same hardware. The previous `~/git/MuSoHu` deployment has been retired.

## Set time before starting an offline session

After a battery swap, connect through the helmet hotspot or the same LAN and
click **Sync from this phone** while sensors/recording are stopped. The phone
supplies UTC without internet. The app disables NTP, applies UTC, then waits
for LiDAR PTP lock and verifies actual packet time. A missing/unlocked LiDAR
is reported separately from successful host time setting. Hardware starts
require a valid phone or NTP reference; phone references expire on reboot or
after 24 hours. Do not change time during recording or an active sensor launch.

The new time card shows phone time, Jetson time and the current reference.
**Use internet time** re-enables NTP when online; wait for it to synchronize.
No timezone change is needed. [Clock workflow](../musohu_ws/README.md#session-clocks).
On a clean host, run `scripts/setup/setup_time_sync_permissions.sh` as the
normal service user first for a manual preview; `--install` deployment invokes
it automatically. The helper uses sudo for its narrow permission file.

## Record a session

1. Start the helmet sensors (including the native recorder), or start dummy
   publishers and a standalone recorder as described below.
2. Choose Full rig (unrectified packed BGR8 uncompressed), Separate RGB,
   Odometry evaluation or Dummy sensors. Both RGB choices retain 1280×720
   per eye and both CameraInfo streams. Edit the topic list
   if needed and enter a label using letters, digits, underscores or hyphens.
3. Start recording. **Starting** covers publisher discovery and recorder
   subscription setup. **Recording** appears only after the C++ recorder confirms all
   selected subscriptions. Missing publishers produce **Failed** with a reason.
4. Stop recording and wait for **Bag finalized** and the saved message count.
   Stop during startup cancels the request. A forced termination is reported
   as failure instead of a successful save.

Recorder storage, buffering and compression are configured in
[bag_recorder_config.yml](bag_recorder_config.yml). The web recorder reads it
at the start of **each new session**, so changes need no service/sensor restart
and do not alter a bag already recording.

The file is a compatibility symlink to the canonical ROS package configuration,
[`musohu_bag_recorder/config/bag_recorder_config.yml`](../musohu_ws/src/musohu_bag_recorder/config/bag_recorder_config.yml).
The C++ node is launched with helmet bringup and owns subscriptions and the
writer. `recording_worker.py` performs preflight/provenance and calls
`/musohu/recorder/start`, `/stop` and `/get_state`; it does not spawn a rosbag CLI.
The native package's [service contract](../musohu_ws/src/musohu_bag_recorder/README.md)
also documents direct ROS and command-line recording.

Current maintainer-selected settings:

```yaml
storage: mcap
serialization_format: ""
max_cache_size: 500000000
compression_mode: none
compression_format: zstd
compression_queue_size: 1
compression_threads: 0
```

`max_cache_size` is bytes per buffer (500 MB here); double buffering can use
about 1 GB. Zero writes messages directly without the cache. The code fallback
when this key is omitted remains 100 MiB; the explicit YAML value takes precedence.
`storage` chooses the installed rosbag2 writer (`mcap` produces `.mcap`;
`sqlite3` produces `.db3`). Setup installs both; MCAP is the default.
`serialization_format: ""` keeps the middleware's native CDR format on this
Jetson. A nonempty serialization format needs a registered converter; native
CDR does not need one. Humble's MCAP plugin defaults to uncompressed indexed
chunks; `compression_mode: none` retains that behavior.

Bag compression is independent of JPEG image compression. Set
`compression_mode` to `file` or `message` to enable the selected compressor;
`zstd` is installed here. Compression format/queue/thread flags are omitted
when mode is `none`. Threads `0` lets ROS use the CPU core count; set an explicit
count to limit compression workers. MCAP does not support rosbag2 message
compression. Invalid YAML, unknown keys, invalid values or unavailable plugins
produce a failed session with a reason before a bag is created. There is no
silent fallback to different settings.

Session JSON saves the config path, SHA-256, effective settings, recorder
command and final storage/serialization/compression metadata. For development,
`MUSOHU_BAG_RECORDER_CONFIG=/absolute/path.yml` selects an alternate file.
The `musohu_ws/scripts/record-evaluation.sh` CLI helper uses the same native
recorder and per-session settings as the web client.

The Sensor health panel polls `/api/sensors/health` once per second. Combined
sensor bringup supplies a lightweight ROS rate monitor: WitMotion IMU 200 Hz,
ZED odometry 30 Hz and stamped audio 15.625 messages/s (16 kHz audio in
1,024-sample chunks). Healthy means within ±10% of expected; ±5% is the target,
with a caution note between those limits. Startup, missing data, disabled
sensors and an expired monitor are shown separately. LiDAR rate is explicitly
not monitored. This does not check JPEG throughput or tracking accuracy: the
current pilot retained about 16.6 Hz stereo images despite approximately 30 Hz
odometry. See [workspace monitoring details](../musohu_ws/README.md#sensor-rate-health).

Bags use `<label>_<UTC timestamp>_<unique suffix>`. Existing output is never
replaced. Each bag has adjacent `.session.json` and `.recorder.log` files.
Metadata includes selected/available topic types and QoS, source SHAs and dirty
state, SDK, project YAML contents/hashes, effective ZED parameters, selected phone/NTP
reference and host clock state, timestamps, bag
counts and finalization status. Publishers can exist without sending data;
final results explicitly list any topics with zero messages.

Full rig records packed unrectified BGR8 uncompressed stereo and both camera calibrations (no
dense depth), LiDAR, both IMU sources including calibrated/raw ZED IMUs,
ZED trajectories/tracking status, timestamped audio, audio format/DOA/VAD, TF
and diagnostics. Images and LiDAR clouds consume substantial storage. Inspect Disk
Space and use the smaller odometry preset when images/audio are unnecessary.
[Session clocks](../musohu_ws/README.md#session-clocks) documents timestamp sources.

Normal API shutdown asks the native recorder to finalize before stopping the
sensor launch. The recording supervisor also requests finalization on unexpected
API death. If the worker is killed without cleanup, an 8-second steady-clock
owner lease closes the bag and records an owner-loss failure. Native recorder
shutdown closes its writer; matching explicit finalization metadata can be
reconciled when a final service response is unavailable.
API status describes the current owner; after restarting the API, inspect the
saved session JSON and bag metadata for previous sessions. Sensor launch
status indicates the launch process is running; check `/diagnostics` and
actual streams to establish sensor health.

## Develop without helmet hardware

Use the same isolated ROS domain for publishers and web process. Do not click
Start helmet sensors for the dummy workflow. In three terminals, from repo root:

```bash
source /opt/ros/humble/setup.bash
source musohu_ws/install/setup.bash
ROS_DOMAIN_ID=97 python3 musohu_ws/scripts/dummy-sensors.py
```

```bash
source /opt/ros/humble/setup.bash
source musohu_ws/install/setup.bash
ROS_DOMAIN_ID=97 ros2 launch musohu_bag_recorder recorder.launch.py \
  bag_directory:=/tmp/musohu-dev-bags
```

```bash
ROS_DOMAIN_ID=97 MUSOHU_BAG_DIR=/tmp/musohu-dev-bags \
  web-app/venv/bin/python -m uvicorn app:app --app-dir web-app \
  --host 0.0.0.0 --port 8001 --workers 1
```

Choose Dummy sensors. Synthetic IMU, XYZIRT clouds, odometry and timestamped
PCM audio use `/musohu_dummy/*`, leaving hardware topic names distinct.

## Verification

```bash
web-app/venv/bin/pip install -r web-app/requirements-dev.txt
web-app/venv/bin/python -m unittest discover -s web-app/tests -v
source /opt/ros/humble/setup.bash
source musohu_ws/install/setup.bash
ros2 bag info ~/helmet_bags/<session>
# Replay separately from live hardware:
ROS_DOMAIN_ID=98 ros2 bag play ~/helmet_bags/<session>
```

The API tests use the real native C++ recorder and dummy publishers on isolated
domain 99. They cover concurrent starts, invalid inputs, missing publishers,
flush/restart, Stop during discovery, restart during Stop cleanup, worker
failure, native session ownership, unavailable services, owner-lease cleanup,
native node shutdown and API-process death. Compression tests read the saved
bags back through rosbag2, and settings tests inspect native recorder metadata.
A fresh Python environment and desktop/mobile recording were validated on this
Jetson; full provisioning on a clean OS remains open. See the
[workspace workflow](../musohu_ws/README.md) for current defaults.

## Optional MCAP compression after Stop

The nominal middleware is tuned Zenoh; sensor/recorder data use SHM and web
control RPCs use loopback TCP. See the [workspace README](../musohu_ws/README.md)
for middleware switching, DDS bag conversion and storage estimates.

Automatic rewriting is **disabled**. To opt in for the next session, edit:

```yaml
ros:
  mcap_postprocess:
    enabled: true
    executable: /usr/local/bin/mcap
    timeout_seconds: 1800
```

No web restart is needed. When enabled, Stop finalizes the native writer, then
returns HTTP 202 while the UI reports Zstd compression and full verification.
The next recording waits for completion. Verified copies atomically replace the
originals at the same paths; failures preserve a usable bag. Internal chunk
compression needs no outer decompression for playback. `mcap_postprocess.json`
records results. The pinned CLI is installed by setup/deployment or
`musohu_ws/scripts/mcap-cli.sh --install`. Native writer settings remain in
`bag_recorder_config.yml`; this feature does not change capture settings.

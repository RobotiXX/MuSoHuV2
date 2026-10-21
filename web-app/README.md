# Web control and recording

FastAPI/Uvicorn controls this repository's `musohu_ws` and records selected ROS 2
streams with confirmed start/stop state. The app does not require a hotspot;
open the Jetson's current LAN address and the configured port.

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

The existing deployed service on port 8000 uses `~/git/MuSoHu`; changing this
checkout does not update it. A deliberate migration is a separate step:

```bash
./scripts/deploy/setup_production_web_service.sh --install --port 8000
```

That command requests sudo to replace/restart `musohu-web.service`; it does
not configure a hotspot, DNS or firewall. See [deployment details](../scripts/deploy/README.md).

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
No timezone change is needed. [Full clock workflow](../musohu_ws/TIME_SYNC.md).
On a clean host, run `scripts/setup/setup_time_sync_permissions.sh` as the
normal service user first for a manual preview; `--install` deployment invokes
it automatically. The helper uses sudo for its narrow permission file.

## Record a session

1. Start the helmet sensors, or start dummy publishers as described below.
2. Choose Full rig, Odometry evaluation or Dummy sensors. Edit the topic list
   if needed and enter a label using letters, digits, underscores or hyphens.
3. Start recording. **Starting** covers publisher discovery and recorder
   subscription setup. **Recording** appears only after rosbag confirms all
   selected subscriptions. Missing publishers produce **Failed** with a reason.
4. Stop recording and wait for **Bag finalized** and the saved message count.
   Stop during startup cancels the request. A forced termination is reported
   as failure instead of a successful save.

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

Full rig records left/right JPEG stereo and both camera calibrations (no
dense depth), LiDAR, both IMU sources including calibrated/raw ZED IMUs,
ZED trajectories/tracking status, timestamped audio, audio format/DOA/VAD, TF
and diagnostics. Compressed images and LiDAR clouds still consume substantial storage. Inspect Disk
Space and use the smaller odometry preset when images/audio are unnecessary.
[Time synchronization](../musohu_ws/TIME_SYNC.md) documents timestamp limits.

Normal API shutdown interrupts and reaps its process groups and flushes an
active bag. The recording supervisor also finalizes on unexpected API death.
API status describes the current owner; after restarting the API, inspect the
saved session JSON and bag metadata for previous sessions. Sensor launch
status indicates the launch process is running; check `/diagnostics` and
actual streams to establish sensor health.

## Develop without helmet hardware

Use the same isolated ROS domain for publishers and web process. Do not click
Start helmet sensors for the dummy workflow. In two terminals, from repo root:

```bash
source /opt/ros/humble/setup.bash
source musohu_ws/install/setup.bash
ROS_DOMAIN_ID=97 python3 musohu_ws/scripts/dummy-sensors.py
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

The API tests use real ROS/rosbag processes and dummy publishers on isolated
domain 99. They cover concurrent starts, invalid inputs, missing publishers,
flush/restart, Stop during discovery, restart during Stop cleanup, worker
failure and API-process death.
Actual desktop/mobile browser and hardware recording results are in
[VALIDATION.md](../musohu_ws/VALIDATION.md). A fresh Python environment was
validated on this Jetson; full provisioning on a clean OS remains open.

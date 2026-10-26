# MuSoHu service recorder

Adapted from ScoutMini's `rwd_bag_recorder` at the maintainer's request; see
[UPSTREAM.md](UPSTREAM.md) for the source revision and Apache-2.0 attribution.
This package is project-owned. No ScoutMini navigation interfaces are required.

The C++ node receives serialized messages and writes them directly with
`rosbag2_cpp::Writer`. It stays idle until triggered. Helmet bringup launches
it by default; `launch_recorder:=false` disables that node. Web and CLI
clients use the same services and never spawn a second recorder process.

| Service | Type | Purpose |
| --- | --- | --- |
| `/musohu/recorder/start` | `musohu_bag_recorder/srv/TriggerBagRecording` | Open one session with selected topics/settings |
| `/musohu/recorder/stop` | `musohu_bag_recorder/srv/StopBagRecording` | Stop that owner and flush/close the bag |
| `/musohu/recorder/get_state` | `musohu_bag_recorder/srv/GetBagRecordingState` | Read state; optionally renew the matching owner's lease |

`/musohu/recorder/state` publishes small JSON status messages at roughly 1 Hz
with reliable/transient-local QoS. States are starting, recording, stopping,
stopped and failed. `recording` requires subscriptions to every requested
topic. The writer may receive already available topics during startup.
Late publishers are discovered periodically; a web startup timeout stops the
session if selected subscriptions cannot be confirmed.

Same-owner Start is idempotent and retains the original topic/settings
snapshot. A competing owner's Start/Stop is rejected. Bags cannot overwrite
existing paths, and requested paths must remain inside `output_directory`.

## Configuration and timestamps

[config/bag_recorder_config.yml](config/bag_recorder_config.yml) is canonical;
`web-app/bag_recorder_config.yml` is a compatibility symlink to that file.
Storage, native/converter format, cache and none/file/message compression are
supported. Direct Start loads the config per session. The web client validates
plugins and supplies its immutable per-session settings snapshot instead.
Changes apply to the next session. Topic selection remains in the web UI and
helmet manifests, or the service request's explicit `topics` array.

`setup.sh` installs both `sqlite3` (`.db3` files) and `mcap` (`.mcap` files)
storage plugins. Uncompressed MCAP is the default; keep
`compression_mode: none` for this Humble plugin's default uncompressed chunks.
This setting does not change camera transport or image encoding. See the
[workspace workflow](../../README.md#recording-and-archival) for defaults and storage estimates.

QoS adapts to publisher offers using rosbag2's Humble adaptation helper,
including transient-local TF/audio-info publishers. Sensor headers
and serialized payloads remain intact. The bag index uses **host system time
at the serialized subscription callback**, as in the upstream design; it is
not a sensor acquisition timestamp or a hardware synchronization claim.
Use the accepted phone/NTP/PTP workflow before starting hardware.

Stop acknowledges success only after writer close, `metadata.yaml` creation,
and atomic `recording_metadata.json` finalization. That JSON retains the
session identity, selected/discovered topics, callback counts, settings,
RMW, timestamp source and client provenance. The web's adjacent `.session.json`
retains actual stored counts read from rosbag metadata, which can differ from
callback counts if a storage/cache failure occurs.

The web client renews an **8-second steady-clock owner lease**. If it is killed
without cleanup, the node closes the bag and records an owner-loss failure.
Normal web shutdown requests Stop first. Native node shutdown also closes an
active writer; the client can reconcile that explicit native finalization
record if ROS shuts down before the final service response. It does not infer
success merely from a bag directory existing.

## Standalone / dummy development

From the repository root:

```bash
source /opt/ros/humble/setup.bash
source musohu_ws/install/setup.bash
ROS_DOMAIN_ID=97 ros2 launch musohu_bag_recorder recorder.launch.py \
  bag_directory:=/tmp/musohu-dev-bags
```

Run dummy publishers and the web app in the same domain and middleware. See
the [web development guide](../../../web-app/README.md). Direct service use:

```bash
ros2 service call /musohu/recorder/start musohu_bag_recorder/srv/TriggerBagRecording \
  "{session_id: manual_example, reason: manual, topics: [/musohu_dummy/imu]}"
ros2 service call /musohu/recorder/stop musohu_bag_recorder/srv/StopBagRecording \
  "{session_id: manual_example}"
```

Direct requests default to no owner lease (`owner_timeout_sec: 0`); their
caller must stop them explicitly. Web and CLI clients use lease renewal.
For metadata-rich CLI recording, use `musohu_ws/scripts/record-evaluation.sh`.

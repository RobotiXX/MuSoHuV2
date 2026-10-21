#!/usr/bin/env python3
"""Observe a running rig without commanding hardware or changing parameters.

Run after sourcing musohu_ws/install/setup.bash. Rates describe this subscriber's
observations, not a guaranteed sensor rate. No drift/calibration claim is made.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=30.0)
    parser.add_argument('--output', type=Path, required=True,
                        help='New JSON report path; existing files are preserved.')
    parser.add_argument('--sensors', nargs='+', choices=['imu', 'lidar', 'audio', 'zed'],
                        default=['imu', 'lidar', 'audio', 'zed'])
    args = parser.parse_args()
    if not math.isfinite(args.duration) or args.duration <= 0 or args.output.exists():
        parser.error('Duration must be positive and output must not already exist.')

    import numpy as np
    import rclpy
    from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
    from rosidl_runtime_py.utilities import get_message

    expected = {
        'imu': {'/witmotion_imu/imu': 'sensor_msgs/msg/Imu'},
        'lidar': {'/rslidar_points': 'sensor_msgs/msg/PointCloud2'},
        'audio': {'/audio': 'audio_common_msgs/msg/AudioData',
                  '/audio_stamped': 'audio_common_msgs/msg/AudioDataStamped'},
        'zed': {
            '/zed2i/zed_node/imu/data': 'sensor_msgs/msg/Imu',
            '/zed2i/zed_node/imu/data_raw': 'sensor_msgs/msg/Imu',
            '/zed2i/zed_node/odom': 'nav_msgs/msg/Odometry',
            '/zed2i/zed_node/pose': 'geometry_msgs/msg/PoseStamped',
            '/zed2i/zed_node/pose/status': 'zed_msgs/msg/PosTrackStatus',
            '/zed2i/zed_node/left/color/rect/image/compressed': 'sensor_msgs/msg/CompressedImage',
            '/zed2i/zed_node/right/color/rect/image/compressed': 'sensor_msgs/msg/CompressedImage',
            '/zed2i/zed_node/left/color/rect/camera_info': 'sensor_msgs/msg/CameraInfo',
            '/zed2i/zed_node/right/color/rect/camera_info': 'sensor_msgs/msg/CameraInfo',
        },
    }
    topics = {k: v for sensor in args.sensors for k, v in expected[sensor].items()}
    records = {topic: {'type': typ, 'count': 0, 'nonincreasing_stamps': 0}
               for topic, typ in topics.items()}
    stamps = {topic: [] for topic in topics}
    arrivals = {topic: [] for topic in topics}
    latencies = {topic: [] for topic in topics}
    audio_squares = {'/audio': [], '/audio_stamped': []}
    imu_accel = {topic: [] for topic, typ in topics.items() if typ.endswith('/Imu')}
    issues = []
    tracking_states = Counter()
    tf_parents = defaultdict(set)

    def receive(topic, msg):
        rec = records[topic]
        rec['count'] += 1
        arrivals[topic].append(time.monotonic())
        if hasattr(msg, 'header'):
            stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            if stamps[topic] and stamp <= stamps[topic][-1]:
                rec['nonincreasing_stamps'] += 1
            stamps[topic].append(stamp)
            latencies[topic].append(time.time() - stamp)
            rec['frame_id'] = msg.header.frame_id
        if topic in imu_accel:
            a = msg.linear_acceleration
            w = msg.angular_velocity
            q = msg.orientation
            imu_accel[topic].append([a.x, a.y, a.z])
            rec['last_gyro_rad_s'] = [w.x, w.y, w.z]
            rec['last_orientation_norm'] = float(np.linalg.norm([q.x, q.y, q.z, q.w]))
            rec['orientation_covariance_0'] = msg.orientation_covariance[0]
        if topics[topic].endswith('/Image'):
            rec['image'] = {'width': msg.width, 'height': msg.height,
                            'encoding': msg.encoding, 'bytes': len(msg.data)}
            if msg.encoding == '32FC1':
                values = np.frombuffer(msg.data, dtype='>f4' if msg.is_bigendian else '<f4')
                rec['depth_finite_fraction'] = float(np.isfinite(values).mean())
        if topics[topic].endswith('/CompressedImage'):
            rec['compressed_image'] = {'format': msg.format, 'bytes': len(msg.data)}
        if topic in audio_squares:
            data = msg.audio.data if topic == '/audio_stamped' else msg.data
            rec['last_chunk_bytes'] = len(data)
            values = np.frombuffer(bytes(data), dtype='<i2').astype(float)
            audio_squares[topic].append(float(np.mean(values ** 2)))
        if topic == '/rslidar_points' and rec['count'] == 1:
            rec['cloud'] = {'width': msg.width, 'height': msg.height,
                            'point_step': msg.point_step,
                            'fields': [f.name for f in msg.fields]}
            # Sample packed fields directly, respecting per-row padding.
            for name, code in [('ring', 'u2'), ('timestamp', 'f8'), ('x', 'f4')]:
                field = next((f for f in msg.fields if f.name == name), None)
                if field is None:
                    continue
                values = np.ndarray((msg.height, msg.width),
                                    dtype=('>' if msg.is_bigendian else '<') + code,
                                    buffer=msg.data, offset=field.offset,
                                    strides=(msg.row_step, msg.point_step))
                finite = values[np.isfinite(values)]
                rec['cloud'][name] = {'min': float(finite.min()) if finite.size else None,
                                      'max': float(finite.max()) if finite.size else None}
                if name == 'ring':
                    rec['cloud']['rings'] = [int(v) for v in np.unique(values)]
        if topics[topic].endswith('/Odometry'):
            p = msg.pose.pose.position
            rec['last_position_m'] = [p.x, p.y, p.z]
            rec['child_frame_id'] = msg.child_frame_id
        if topics[topic].endswith('/PosTrackStatus'):
            tracking_states[msg.odometry_status] += 1
            rec['last_spatial_memory_status'] = msg.spatial_memory_status
            rec['last_pose_confidence'] = msg.pose_confidence

    rclpy.init()
    node = rclpy.create_node('musohu_validation')
    subscriptions = [node.create_subscription(
        get_message(typ), topic, lambda msg, topic=topic: receive(topic, msg),
        # The SDK offers reliable clouds. Match it for large fragmented data;
        # a best-effort observer can drop clouds even when rosbag retains all.
        QoSProfile(depth=10) if topic == '/rslidar_points' else qos_profile_sensor_data)
        for topic, typ in topics.items()]
    diagnostics = {}
    def on_diagnostics(msg):
        for status in msg.status:
            diagnostics[status.name] = {
                'level': status.level[0] if isinstance(status.level, bytes) else int(status.level),
                'message': status.message,
                'values': {item.key: item.value for item in status.values}}
    subscriptions.append(node.create_subscription(
        get_message('diagnostic_msgs/msg/DiagnosticArray'), '/diagnostics',
        on_diagnostics, qos_profile_sensor_data))
    def on_tf(msg):
        for transform in msg.transforms:
            tf_parents[transform.child_frame_id].add(transform.header.frame_id)
    subscriptions.append(node.create_subscription(
        get_message('tf2_msgs/msg/TFMessage'), '/tf', on_tf, qos_profile_sensor_data))
    subscriptions.append(node.create_subscription(
        get_message('tf2_msgs/msg/TFMessage'), '/tf_static', on_tf,
        QoSProfile(depth=20, durability=DurabilityPolicy.TRANSIENT_LOCAL)))
    start = time.monotonic()
    while time.monotonic() - start < args.duration:
        rclpy.spin_once(node, timeout_sec=0.1)
    graph = dict(node.get_topic_names_and_types())
    publishers = {topic: len(node.get_publishers_info_by_topic(topic)) for topic in topics}
    node.destroy_node()
    rclpy.shutdown()
    for topic, rec in records.items():
        times = arrivals[topic]
        rec['publishers'] = publishers[topic]
        rec['observed_hz'] = (len(times) - 1) / (times[-1] - times[0]) if len(times) > 1 else 0.0
        if rec['count'] < 2:
            issues.append(f'{topic}: fewer than two messages')
        if rec['nonincreasing_stamps']:
            issues.append(f'{topic}: duplicate/backward header timestamps')
        if latencies[topic]:
            rec['header_age_s'] = {'median': float(np.median(latencies[topic])),
                                   'max': float(max(latencies[topic]))}
        if len(stamps[topic]) > 1:
            rec['header_period_s'] = {'median': float(np.median(np.diff(stamps[topic]))),
                                      'max': float(max(np.diff(stamps[topic])))}
        if topic in imu_accel and imu_accel[topic]:
            values = np.array(imu_accel[topic])
            rec['accel_mean_m_s2'] = values.mean(axis=0).tolist()
            rec['accel_std_m_s2'] = values.std(axis=0).tolist()
            if not np.isfinite(values).all():
                issues.append(f'{topic}: nonfinite acceleration')
    for topic, values in audio_squares.items():
        if values:
            records[topic]['rms_pcm16'] = float(np.sqrt(np.mean(values)))
    if 'zed' in args.sensors:
        records['/zed2i/zed_node/pose/status']['odometry_status_counts'] = dict(tracking_states)
        if not tracking_states[0]:
            issues.append('No ZED odometry status OK observed')
    for child, parents in tf_parents.items():
        if len(parents) > 1:
            issues.append(f'TF child {child} has multiple parents: {sorted(parents)}')
    cloud = records.get('/rslidar_points', {}).get('cloud', {})
    if 'lidar' in args.sensors and not {'ring', 'timestamp'}.issubset(cloud.get('fields', [])):
        issues.append('LiDAR has no per-point ring/timestamp fields')
    report = {'utc': datetime.now(timezone.utc).isoformat(), 'duration_s': args.duration,
              'topics': records, 'diagnostics': diagnostics, 'graph': graph, 'issues': issues,
              'tf_parents': {k: sorted(v) for k, v in tf_parents.items()},
              'limits': 'Short acquisition check; no drift, calibration or sustained-rate validation.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report_text = json.dumps(report, indent=2, allow_nan=False) + '\n'
    with args.output.open('x') as stream:
        stream.write(report_text)
    print(json.dumps({'report': str(args.output), 'issues': issues,
                      'rates_hz': {t: round(v['observed_hz'], 2) for t, v in records.items()}}, indent=2))
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Count lightweight streams; publish diagnostics and an atomic web snapshot."""
import json
import os
from pathlib import Path
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from audio_common_msgs.msg import AudioDataStamped
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu

from sensor_health_model import RateWindow


class SensorHealthMonitor(Node):
    def __init__(self):
        super().__init__('musohu_sensor_health')
        def param(name, value):
            return self.declare_parameter(name, value).value
        settings = dict(window_s=param('window_s', 10.0), warmup_s=param('warmup_s', 5.0),
                        stale_s=param('stale_s', 2.0),
                        target_tolerance=param('target_tolerance', 0.05),
                        healthy_tolerance=param('healthy_tolerance', 0.10))
        self.path = Path(param('state_file', os.environ.get('MUSOHU_HEALTH_FILE',
                         '~/.local/state/musohu/sensor_health.json'))).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        self.started = time.monotonic()
        self.streams = {}
        self.subscriptions_owned = []
        for key, label, topic, cls, rate in [
            ('witmotion', 'WitMotion IMU', '/witmotion_imu/imu', Imu, 200.0),
            ('zed', 'ZED odometry', '/zed2i/zed_node/odom', Odometry, 30.0),
            ('audio', 'ReSpeaker audio', '/audio_stamped', AudioDataStamped, 15.625),
        ]:
            enabled = param(key + '.enabled', True)
            topic = param(key + '.topic', topic)
            window = RateWindow(param(key + '.expected_hz', rate), self.started, **settings)
            self.streams[key] = (label, topic, enabled, window)
            if enabled:
                self.subscriptions_owned.append(self.create_subscription(
                    cls, topic, lambda msg, w=window: w.receive(time.monotonic()),
                    qos_profile_sensor_data))
        self.publisher = self.create_publisher(DiagnosticArray, '/diagnostics', 10)
        period = param('report_period_s', 1.0)
        if not 0.2 <= period <= 10:
            raise ValueError('report_period_s must be between 0.2 and 10 seconds')
        self.create_timer(period, self.report)
        self.report()

    def report(self):
        now = time.monotonic()
        sensors, diagnostics = {}, []
        for key, (label, topic, enabled, window) in self.streams.items():
            snapshot = dict(window.snapshot(now, enabled), label=label, topic=topic)
            sensors[key] = snapshot
            state = snapshot['status']
            level = (DiagnosticStatus.OK if state == 'healthy' else DiagnosticStatus.ERROR
                     if state == 'missing' else DiagnosticStatus.WARN
                     if state == 'unhealthy' else DiagnosticStatus.STALE)
            diagnostics.append(DiagnosticStatus(
                name='MuSoHu sensors/' + key, hardware_id=topic, level=level,
                message=snapshot['reason'], values=[KeyValue(key=k, value=str(v))
                    for k, v in snapshot.items() if v is not None]))
        sensors['lidar'] = dict(label='LiDAR', topic=None, status='not_monitored',
                               healthy=False, expected_hz=None, observed_hz=None,
                               reason='Point-cloud receive rate intentionally not monitored')
        state = dict(schema_version=1, boot_id=self.boot_id, pid=os.getpid(),
                     ros_domain_id=os.environ.get('ROS_DOMAIN_ID', '0'),
                     updated_monotonic_s=now, updated_epoch_s=time.time(), sensors=sensors)
        temporary = self.path.with_name(self.path.name + '.' + str(os.getpid()) + '.tmp')
        temporary.write_text(json.dumps(state, allow_nan=False) + '\n')
        temporary.replace(self.path)
        message = DiagnosticArray(status=diagnostics)
        message.header.stamp = self.get_clock().now().to_msg()
        self.publisher.publish(message)


def main():
    rclpy.init()
    node = SensorHealthMonitor()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()

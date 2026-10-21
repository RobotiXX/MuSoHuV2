"""Read atomic monitor snapshots; never retain a healthy state after expiry."""
import json
import os
from pathlib import Path
import time

import yaml


def read_sensor_health(manager, now=None, boot_id=None, domain_id=None):
    now = time.monotonic() if now is None else now
    boot_id = (Path('/proc/sys/kernel/random/boot_id').read_text().strip()
               if boot_id is None else boot_id)
    domain_id = os.environ.get('ROS_DOMAIN_ID', '0') if domain_id is None else domain_id
    reason = 'Sensor monitor is not running'
    try:
        if manager.health_path.stat().st_size > 65536:
            raise ValueError('Oversized health snapshot')
        state = json.loads(manager.health_path.read_text())
        age = now - float(state['updated_monotonic_s'])
        if state['boot_id'] != boot_id:
            reason = 'Sensor monitor snapshot is from a previous boot'
        elif str(state['ros_domain_id']) != str(domain_id):
            reason = 'Sensor monitor is on a different ROS domain'
        elif not 0 <= age <= 4.0:
            reason = 'Sensor monitor stopped reporting'
        elif not isinstance(state['sensors'], dict):
            raise ValueError('Invalid sensor states')
        else:
            return dict(state, monitor_online=True, snapshot_age_s=age,
                        limits='Receive rate only; does not establish sensor accuracy, image recording or tracking quality.')
    except (OSError, ValueError, KeyError, TypeError):
        pass
    config_path = manager.workspace / 'src/helmet_bringup/config/sensor_health.yaml'
    try:
        params = yaml.safe_load(config_path.read_text())['musohu_sensor_health']['ros__parameters']
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError):
        params = {}
    sensors = {}
    for key, label in [('witmotion','WitMotion IMU'), ('zed','ZED odometry'), ('audio','ReSpeaker audio')]:
        stream = params.get(key, {})
        sensors[key] = dict(label=label, topic=stream.get('topic'),
                            expected_hz=stream.get('expected_hz'), observed_hz=None,
                            status='offline', healthy=False, reason=reason)
    sensors['lidar'] = dict(label='LiDAR', status='not_monitored', healthy=False,
                           expected_hz=None, observed_hz=None,
                           reason='Point-cloud receive rate intentionally not monitored')
    return dict(monitor_online=False, sensors=sensors, message=reason)

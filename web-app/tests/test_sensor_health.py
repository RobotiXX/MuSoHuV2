"""The UI must not keep showing a healthy sensor after monitor failure/reboot."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sensor_health import read_sensor_health


class SensorHealthTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = SimpleNamespace(health_path=Path(self.temp.name)/'health.json',
                                      workspace=Path(__file__).resolve().parents[2]/'musohu_ws')

    def state(self, **overrides):
        payload = dict(boot_id='this-boot', ros_domain_id='0', updated_monotonic_s=100,
                       sensors={'zed':dict(status='healthy', healthy=True, observed_hz=30)})
        payload.update(overrides)
        self.manager.health_path.write_text(json.dumps(payload))
        return read_sensor_health(self.manager, now=101, boot_id='this-boot', domain_id='0')

    def test_fresh_snapshot(self):
        self.assertTrue(self.state()['monitor_online'])

    def test_old_future_boot_and_domain_snapshots_are_offline(self):
        for overrides in [dict(updated_monotonic_s=90), dict(updated_monotonic_s=110),
                          dict(boot_id='previous-boot'), dict(ros_domain_id='99')]:
            with self.subTest(overrides=overrides):
                state = self.state(**overrides)
                self.assertFalse(state['monitor_online'])
                self.assertFalse(state['sensors']['zed']['healthy'])

    def test_missing_and_invalid_snapshots(self):
        self.assertFalse(read_sensor_health(self.manager)['monitor_online'])
        self.manager.health_path.write_text('{invalid')
        self.assertFalse(read_sensor_health(self.manager)['monitor_online'])


if __name__ == '__main__':
    unittest.main()

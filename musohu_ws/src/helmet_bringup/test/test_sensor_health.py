"""Rate boundaries, startup, stale streams and recovery without wall-clock time."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from sensor_health_model import RateWindow


class RateHealthTest(unittest.TestCase):
    def stream(self, rate):
        window = RateWindow(200, 0)
        for i in range(round(rate * 10) + 1):
            window.receive(i / rate)
        return window

    def test_ten_percent_is_healthy_and_five_percent_is_target(self):
        for rate, healthy, target in [(200, True, True), (190, True, True),
                                      (185, True, False), (180, True, False),
                                      (220, True, False), (175, False, False),
                                      (225, False, False)]:
            with self.subTest(rate=rate):
                # Just after the first point leaves the full ten-second window.
                state = self.stream(rate).snapshot(10.001)
                self.assertEqual(state['healthy'], healthy)
                self.assertEqual(state['target_met'], target)

    def test_missing_after_startup_and_disabled(self):
        window = RateWindow(200, 0)
        self.assertEqual(window.snapshot(1)['status'], 'starting')
        self.assertEqual(window.snapshot(6)['status'], 'missing')
        self.assertEqual(window.snapshot(6, enabled=False)['status'], 'disabled')

    def test_delayed_sensor_gets_its_own_warmup(self):
        window = RateWindow(200, 0)
        window.receive(20); window.receive(20.005)
        self.assertEqual(window.snapshot(20.005)['status'], 'starting')

    def test_stopped_stream_expires_and_recovers(self):
        window = self.stream(200)
        self.assertEqual(window.snapshot(10.001)['status'], 'healthy')
        self.assertEqual(window.snapshot(12.1)['status'], 'missing')
        for i in range(2401, 5001):
            window.receive(i / 200)
        self.assertEqual(window.snapshot(25.001)['status'], 'healthy')

    def test_invalid_settings_fail(self):
        for rate in [0, -1, float('nan')]:
            with self.assertRaises(ValueError): RateWindow(rate, 0)


if __name__ == '__main__':
    unittest.main()

"""Protect against silently publishing device timestamps before PTP lock."""
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_lidar_clock import check


class ClockCheckTest(unittest.TestCase):
    def test_host_time_mode_never_contacts_sensor(self):
        with patch('check_lidar_clock.urllib.request.urlopen') as fetch:
            check({'lidar': [{'driver': {'use_lidar_clock': False}}]})
            fetch.assert_not_called()

    def test_unlocked_refuses_before_opening_udp(self):
        response = io.BytesIO(b'<input name="ptp_remote_sync_status_text" value="UnLock">')
        with patch('check_lidar_clock.urllib.request.urlopen', return_value=response), \
                patch('check_lidar_clock.socket.socket') as sock:
            with self.assertRaisesRegex(RuntimeError, 'wait for lock'):
                check({'lidar': [{'driver': {'use_lidar_clock': True}}]})
            sock.assert_not_called()

    def test_locked_but_wrong_epoch_refuses(self):
        response = io.BytesIO(b'<input name="ptp_remote_sync_status_text" value="Locked">')
        packet = bytes.fromhex('55aa055a') + bytes(1244)
        sock = Mock()
        sock.recvfrom.return_value = packet, ('192.168.1.200', 6699)
        with patch('check_lidar_clock.urllib.request.urlopen', return_value=response), \
                patch('check_lidar_clock.socket.socket') as factory, \
                patch('check_lidar_clock.time.monotonic', side_effect=[0, 0, 1]), \
                patch('check_lidar_clock.time.time', return_value=1800000000):
            factory.return_value.__enter__.return_value = sock
            with self.assertRaisesRegex(RuntimeError, 'outside'):
                check({'lidar': [{'driver': {'use_lidar_clock': True}}]})

    def test_unix_epoch_host_refuses_before_contacting_sensor(self):
        with patch('check_lidar_clock.time.time', return_value=100), \
                patch('check_lidar_clock.urllib.request.urlopen') as fetch:
            with self.assertRaisesRegex(RuntimeError, 'sync from phone'):
                check({'lidar': [{'driver': {'use_lidar_clock': True}}]})
            fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()

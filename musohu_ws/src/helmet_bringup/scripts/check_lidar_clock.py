#!/usr/bin/env python3
"""Fail closed before ROS uses an unlocked or wrong-epoch Helios clock."""
import argparse
from html.parser import HTMLParser
import socket
import time
import urllib.request

import yaml


class Inputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and attrs.get('name'):
            self.values[attrs['name']] = attrs.get('value', '')


def check(config):
    driver = config['lidar'][0]['driver']
    if not driver.get('use_lidar_clock', False):
        print('LiDAR uses host-derived timestamps; PTP acquisition-time check skipped.')
        return
    if not 1577836800 <= time.time() < 4102444800:
        raise RuntimeError('Host UTC is implausible; sync from phone or internet before LiDAR bringup.')
    profile = config.get('clock_sync', {})
    address = profile.get('lidar_address', '192.168.1.200')
    age_limit = float(profile.get('max_receive_age_s', 0.1))
    parser = Inputs()
    parser.feed(urllib.request.urlopen(f'http://{address}/cgi-bin/diagnostic_info.cgi',
                                      timeout=3).read().decode('utf-8', errors='replace'))
    status = parser.values.get('ptp_remote_sync_status_text')
    if status != 'Locked':
        raise RuntimeError(f'Helios PTP is {status!r}; wait for lock before bringup.')
    ages = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('', int(driver.get('msop_port', 6699))))
        sock.settimeout(1)
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            data, sender = sock.recvfrom(65535)
            if sender[0] != address or len(data) != 1248 or data[:4] != bytes.fromhex('55aa055a'):
                continue
            stamp = int.from_bytes(data[20:26], 'big') + int.from_bytes(data[26:30], 'big') * 1e-6
            ages.append(time.time() - stamp)
    if not ages or min(ages) < -age_limit or max(ages) > age_limit:
        raise RuntimeError(f'LiDAR packet clock is outside ±{age_limit}s of host receive time: {ages[:3]}')
    print(f'Helios PTP Locked; packet receive age {min(ages):.6f}..{max(ages):.6f}s. '
          'This checks epoch/delivery age, not calibrated synchronization accuracy.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    try:
        with open(args.config) as stream:
            check(yaml.safe_load(stream))
    except Exception as exc:
        parser.exit(1, f'LiDAR clock check failed: {exc}\n')


if __name__ == '__main__':
    main()

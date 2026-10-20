#!/usr/bin/env python3
"""Inspect Helios clock settings, configure PTP, or sample native packet time.

--set-ptp preserves the current parameter form and changes only clock source
and PTP domain. --sample requires the ROS LiDAR driver stopped (UDP ports).
"""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import selectors
import socket
import statistics
import time
import urllib.request
from uuid import uuid4


class ParameterForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.values = {}
        self.select = None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.active = attrs.get('enctype') == 'multipart/form-data' and 'param_setting.cgi' in attrs.get('action', '')
        if not self.active:
            return
        if tag == 'input' and attrs.get('name') and 'disabled' not in attrs:
            kind = attrs.get('type', 'text').lower()
            if kind in ('file', 'button') or kind == 'submit' and attrs['name'] != 'save_param':
                return
            if kind in ('checkbox', 'radio') and 'checked' not in attrs:
                return
            self.values[attrs['name']] = attrs.get('value', 'on')
        if tag == 'select':
            self.select = attrs.get('name')
        if tag == 'option' and self.select:
            if self.select not in self.values or 'selected' in attrs:
                self.values[self.select] = attrs.get('value', '')
    def handle_endtag(self, tag):
        if tag == 'form':
            self.active = False
        if tag == 'select':
            self.select = None


class Inputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and attrs.get('name'):
            self.values[attrs['name']] = attrs.get('value', '')


def fetch(address, page):
    return urllib.request.urlopen(f'http://{address}/cgi-bin/{page}', timeout=5).read().decode('utf-8', errors='replace')


def clock_settings(address):
    form = ParameterForm()
    form.feed(fetch(address, 'param_setting.cgi'))
    info = Inputs()
    info.feed(fetch(address, 'diagnostic_info.cgi'))
    return form.values, {k: v for k, v in info.values.items() if 'ptp' in k.lower() or 'gps' in k.lower() or 'pps' in k.lower()}


def sample_packets(duration):
    poll = selectors.DefaultSelector()
    sockets = []
    ages = []
    modes = []
    try:
        for port in (6699, 7788):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sockets.append(sock)
            try:
                sock.bind(('', port))
            except OSError as exc:
                raise RuntimeError('Stop the ROS LiDAR driver before sampling its UDP ports.') from exc
            sock.setblocking(False)
            poll.register(sock, selectors.EVENT_READ, port)
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            for key, _ in poll.select(timeout=0.1):
                data, sender = key.fileobj.recvfrom(65535)
                received = time.time()
                if key.data == 6699 and len(data) == 1248 and data[:4] == bytes.fromhex('55aa055a'):
                    seconds = int.from_bytes(data[20:26], 'big')
                    micros = int.from_bytes(data[26:30], 'big')
                    ages.append(received - (seconds + micros * 1e-6))
                if key.data == 7788 and len(data) == 1248 and data[:8] == bytes.fromhex('a5ff005a11115555'):
                    # Packed RSHELIOSDifopPkt::time_info offset in the pinned rs_driver.
                    modes.append({'sync_mode': data[301], 'sync_status': data[302]})
        result = {'msop_packets': len(ages), 'difop_clock_states': modes}
        if ages:
            result['host_receive_minus_lidar_seconds'] = {
                'min': min(ages), 'median': statistics.median(ages), 'max': max(ages),
                'p95': sorted(ages)[int(0.95 * (len(ages) - 1))]}
        return result
    finally:
        poll.close()
        for sock in sockets:
            sock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address', default='192.168.1.200')
    parser.add_argument('--set-ptp', action='store_true')
    parser.add_argument('--sample', type=float, default=0, metavar='SECONDS')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.sample) or args.sample < 0 or args.sample > 300:
        parser.error('Sample duration must be between 0 and 300 seconds.')
    if args.output and args.output.exists():
        parser.error('Output already exists; preserve prior evidence and choose a new path.')
    before, diagnostics = clock_settings(args.address)
    report = {'utc': datetime.now(timezone.utc).isoformat(), 'settings': before, 'diagnostics': diagnostics}
    if args.set_ptp:
        if not {'TimeSyncSrc', 'ptp_domain_number', 'device_ip_addr', 'save_param'}.issubset(before):
            raise RuntimeError('Unrecognized parameter form; refusing to change sensor settings.')
        changed = dict(before, TimeSyncSrc='PTP-E2E-L4', ptp_domain_number='0')
        if args.output:
            with Path(str(args.output) + '.before.json').open('x') as stream:
                json.dump(report, stream, indent=2)
        boundary = 'musohu-' + uuid4().hex
        body = ''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
                       for name, value in changed.items()) + f'--{boundary}--\r\n'
        request = urllib.request.Request(f'http://{args.address}/cgi-bin/param_setting.cgi',
                                         data=body.encode(), headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
        urllib.request.urlopen(request, timeout=10).read()
        after, diagnostics = clock_settings(args.address)
        if any(after.get(k) != v for k, v in changed.items()):
            raise RuntimeError('Sensor settings did not match the submitted form; inspect device configuration.')
        report.update(settings_before=before, settings=after, diagnostics=diagnostics)
    if args.sample > 0:
        report['packets'] = sample_packets(args.sample)
        report['settings'], report['diagnostics'] = clock_settings(args.address)
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(text)
    print(text)


if __name__ == '__main__':
    main()

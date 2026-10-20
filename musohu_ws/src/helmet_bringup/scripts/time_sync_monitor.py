#!/usr/bin/env python3
"""Publish clock health without adjusting clocks or changing timestamp sources."""
import argparse
import signal
import subprocess
import urllib.request

import rclpy
from rclpy.signals import SignalHandlerOptions
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
import yaml
from check_lidar_clock import Inputs
from clock_reference import reference_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    args, ros_args = parser.parse_known_args()
    config = yaml.safe_load(open(args.config))
    address = config.get('clock_sync', {}).get('lidar_address', '192.168.1.200')
    native = config['lidar'][0]['driver'].get('use_lidar_clock', False)
    rclpy.init(args=ros_args, signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node('musohu_time_sync')
    publisher = node.create_publisher(DiagnosticArray, '/diagnostics', 10)
    def output(argv):
        try:
            return subprocess.check_output(argv, text=True, stderr=subprocess.DEVNULL, timeout=2).strip()
        except (OSError, subprocess.SubprocessError):
            return 'unknown'
    def publish():
        reference = reference_status()
        values = {'host_ntp_synchronized': output(['timedatectl','show','-p','NTPSynchronized','--value']),
                  'host_reference': reference['source'],
                  'host_reference_ready': str(reference['ready']),
                  'ptp_service': output(['systemctl','is-active','musohu-ptp']),
                  'timestamping': 'software; host-clock based, no PHC',
                  'use_lidar_clock': str(native)}
        try:
            fields = Inputs()
            fields.feed(urllib.request.urlopen(f'http://{address}/cgi-bin/diagnostic_info.cgi', timeout=1).read().decode('utf-8', errors='replace'))
            values['lidar_ptp_status'] = fields.values.get('ptp_remote_sync_status_text', 'unknown')
            values['lidar_reported_master_offset'] = fields.values.get('PTP_Master_Offset_text', 'unknown')
        except Exception as exc:
            values['lidar_ptp_status'] = 'unavailable'
            values['error'] = str(exc)
        level, message = DiagnosticStatus.OK, 'LiDAR PTP locked; software host timing'
        if not native:
            level, message = DiagnosticStatus.WARN, 'LiDAR uses host-derived receive timestamps'
        elif values['lidar_ptp_status'] != 'Locked' or values['ptp_service'] != 'active':
            level, message = DiagnosticStatus.ERROR, 'LiDAR PTP lock/source unavailable; inspect recording timing'
        elif not reference['ready']:
            level, message = DiagnosticStatus.WARN, 'PTP locked; set host time from phone or internet before recording'
        else:
            message += '; UTC reference: ' + reference['source']
        status = DiagnosticStatus(level=level, name='MuSoHu time sync', hardware_id=address,
                                  message=message,
                                  values=[KeyValue(key=k,value=v) for k,v in values.items()])
        msg = DiagnosticArray(status=[status])
        msg.header.stamp = node.get_clock().now().to_msg()
        publisher.publish(msg)
    node.create_timer(5.0, publish)
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        publish()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

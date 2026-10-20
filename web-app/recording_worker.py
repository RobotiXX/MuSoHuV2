"""ROS-aware rosbag supervisor. Run through the configured workspace underlay."""
import argparse
import ctypes
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import re
import signal
import subprocess
import time

import yaml
from process_manager import atomic_json
from clock_sync import reference_status


def utc():
    return datetime.now(timezone.utc).isoformat()


def command_output(argv, cwd=None):
    try:
        return subprocess.check_output(argv, cwd=cwd, text=True, stderr=subprocess.STDOUT,
                                       timeout=5).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return f'unavailable: {exc}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    args = parser.parse_args()
    session = json.loads(args.session.read_text())
    stop_requested = False
    def on_signal(signum, frame):
        nonlocal stop_requested
        stop_requested = True
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    # If the API process crashes, finalize its recording instead of orphaning
    # a recorder. Children are signaled by this supervisor's cleanup below.
    parent_pid = os.getppid()
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGINT, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'Unable to register parent-death signal')
    if parent_pid == 1 or os.getppid() != parent_pid:
        stop_requested = True
    child = None
    node = None
    context_started = False

    def save(**updates):
        session.update(updates)
        atomic_json(args.session, session)

    try:
        import rclpy
        from rclpy.signals import SignalHandlerOptions
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        context_started = True
        node = rclpy.create_node('musohu_recording_preflight_' + str(os.getpid()))
        deadline = time.monotonic() + 8
        publishers = {}
        while not stop_requested and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            publishers = {t: node.get_publishers_info_by_topic(t) for t in session['topics']}
            if all(publishers.values()):
                break
        if stop_requested:
            save(status='stopped', stopped_at=utc(), finalized=False, message='Cancelled before recording began.')
            return 0
        missing = [t for t, endpoints in publishers.items() if not endpoints]
        if missing:
            raise RuntimeError('No publisher for selected topics: ' + ', '.join(missing))
        available = {t: sorted({endpoint.topic_type for endpoint in endpoints})
                     for t, endpoints in publishers.items()}
        if any(len(types) != 1 for types in available.values()):
            raise RuntimeError('Selected topic has conflicting publisher types.')
        qos = {t: [{'node_name': e.node_name, 'node_namespace': e.node_namespace,
                    'type': e.topic_type, 'reliability': int(e.qos_profile.reliability),
                    'durability': int(e.qos_profile.durability)} for e in endpoints]
               for t, endpoints in publishers.items()}
        effective_zed = None
        if any(t.startswith('/zed2i/zed_node/') for t in session['topics']):
            from rcl_interfaces.srv import GetParameters, ListParameters
            from rclpy.parameter import parameter_value_to_python
            names = ['depth.depth_mode','depth.depth_stabilization',
                     'general.grab_resolution','general.grab_frame_rate','general.pub_frame_rate',
                     'general.sdk_timestamp_clock','pos_tracking.pos_tracking_mode',
                     'pos_tracking.compute_preference','pos_tracking.imu_fusion',
                     'pos_tracking.area_memory','sensors.sensors_pub_rate',
                     'video.publish_rgb','video.publish_left_right','depth.publish_depth_map']
            client = node.create_client(GetParameters, '/zed2i/zed_node/get_parameters')
            effective_zed = 'unavailable: parameter service did not respond'
            # Some wrapper parameters are undeclared with depth NONE. Asking for
            # even one undeclared name makes Humble return an empty value list.
            listing = node.create_client(ListParameters, '/zed2i/zed_node/list_parameters')
            if listing.wait_for_service(timeout_sec=2) and client.wait_for_service(timeout_sec=2):
                future = listing.call_async(ListParameters.Request())
                rclpy.spin_until_future_complete(node, future, timeout_sec=3)
                if future.done() and future.result() is not None:
                    declared = set(future.result().result.names)
                    selected = [name for name in names if name in declared]
                    future = client.call_async(GetParameters.Request(names=selected))
                    rclpy.spin_until_future_complete(node, future, timeout_sec=3)
                    if future.done() and future.result() is not None:
                        values = future.result().values
                        if len(values) == len(selected):
                            effective_zed = dict(zip(selected, [parameter_value_to_python(v) for v in values]))
                            effective_zed['_undeclared'] = [name for name in names if name not in declared]
        node.destroy_node()
        node = None
        rclpy.shutdown()
        context_started = False
        repo = Path(session['workspace']).parent
        sdk = Path('/usr/local/zed/zed-config-version.cmake')
        configs = {}
        for path in (Path(session['workspace']) / 'src/helmet_bringup/config').glob('*.yaml'):
            configs[path.name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                  'contents': yaml.safe_load(path.read_text())}
        save(topic_availability=available, publisher_endpoints=qos,
             repository_commit=command_output(['git', 'rev-parse', 'HEAD'], cwd=repo),
             repository_status=command_output(['git', 'status', '--short'], cwd=repo),
             submodules=command_output(['git', 'submodule', 'status', '--recursive'], cwd=repo),
             zed_sdk=sdk.read_text().splitlines()[0] if sdk.exists() else None,
             sensor_configs=configs,
             zed_effective_parameters=effective_zed,
             timestamp_notes={
                 'zed': 'SDK SYSTEM_CLOCK mapping to host; USB camera is not a PTP endpoint.',
                 'lidar': 'Native clock when configured; verify PTP lock and packet epoch separately.',
                 'wt901': 'Host receive timestamps; UART/sensor latency not calibrated.',
                 'audio_stamped': 'PortAudio ADC/current-time pair mapped to host UTC; fallback to receive time.'},
             clock_at_start=command_output(['timedatectl', 'show', '-p', 'NTPSynchronized', '-p', 'NTP']),
             clock_reference_at_start=reference_status(),
             ptp_service=command_output(['systemctl', 'show', 'musohu-ptp', '-p', 'ActiveState']),
             ros_domain_id=os.environ.get('ROS_DOMAIN_ID', '0'))
        bag = Path(session['bag_path'])
        if stop_requested:
            save(status='stopped', stopped_at=utc(), finalized=False, message='Cancelled before recording began.')
            return 0
        recorder_log = Path(str(bag) + '.recorder.log')
        session['recorder_log'] = str(recorder_log)
        with recorder_log.open('x') as log:
            child = subprocess.Popen(['ros2', 'bag', 'record', '-o', str(bag), *session['topics']],
                                     stdout=log, stderr=subprocess.STDOUT,
                                     env=dict(os.environ, RCUTILS_COLORIZED_OUTPUT='0'))
            deadline = time.monotonic() + 15
            ready = False
            while child.poll() is None and not stop_requested:
                text = recorder_log.read_text(errors='replace')
                subscribed = set(re.findall(r"Subscribed to topic ['\"]([^'\"]+)['\"]", text))
                if not ready and 'Recording...' in text and set(session['topics']).issubset(subscribed):
                    ready = True
                    save(status='recording', started_at=utc(), recorder_pid=child.pid)
                if not ready and time.monotonic() > deadline:
                    raise RuntimeError('Recorder did not confirm subscriptions before startup timeout.')
                time.sleep(0.1)
            if stop_requested:
                save(status='stopping')
                # The manager signals our whole group, including the recorder.
                # Relay directly if invoked manually with only this PID signaled.
                try:
                    child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    child.send_signal(signal.SIGINT)
                child.wait(timeout=20)
            code = child.wait(timeout=5)
        metadata_path = bag / 'metadata.yaml'
        if code != 0 or not metadata_path.is_file():
            raise RuntimeError(f'Recorder exited {code}; bag metadata/finalization missing. See {recorder_log}')
        metadata = yaml.safe_load(metadata_path.read_text())['rosbag2_bagfile_information']
        counts = {entry['topic_metadata']['name']: entry['message_count']
                  for entry in metadata['topics_with_message_count']}
        save(status='stopped', stopped_at=utc(), finalized=True, exit_code=code,
             message_count=metadata['message_count'], topic_counts=counts,
             topics_without_messages=[t for t in session['topics'] if not counts.get(t)],
             duration_ns=metadata['duration']['nanoseconds'],
             clock_at_stop=command_output(['timedatectl', 'show', '-p', 'NTPSynchronized', '-p', 'NTP']),
             clock_reference_at_stop=reference_status())
        return 0
    except Exception as exc:
        save(status='failed', error=str(exc), stopped_at=utc(), finalized=False)
        return 1
    finally:
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGINT)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if node is not None:
            node.destroy_node()
        if context_started:
            rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())

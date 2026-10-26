"""ROS service client and session supervisor for the helmet C++ bag recorder."""
import argparse
import ctypes
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import time

import yaml
from process_manager import atomic_json
from clock_sync import reference_status
from bag_recorder_config import load_recorder_config, validate_ros_plugins


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
    # a recorder. Cleanup asks the native node to stop; its lease covers SIGKILL.
    parent_pid = os.getppid()
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGINT, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'Unable to register parent-death signal')
    if parent_pid == 1 or os.getppid() != parent_pid:
        stop_requested = True
    service_attempted = False
    service_closed = False
    stop_client = None
    stop_request = None
    node = None
    context_started = False

    def save(**updates):
        session.update(updates)
        atomic_json(args.session, session)

    def save_finished():
        bag = Path(session['bag_path'])
        native = json.loads((bag / 'recording_metadata.json').read_text())
        if (native.get('session_id') != session['session_id'] or
                native.get('bag_uri') != str(bag) or not native.get('finalized') or
                native.get('status') != 'stopped' or native.get('error')):
            raise RuntimeError('Native recorder has not confirmed this session finalized')
        metadata_path = bag / 'metadata.yaml'
        metadata = yaml.safe_load(metadata_path.read_text())['rosbag2_bagfile_information']
        counts = {entry['topic_metadata']['name']: entry['message_count']
                  for entry in metadata['topics_with_message_count']}
        postprocess_config = session.get('mcap_postprocess_config', {'enabled': False})
        save(status='compressing' if postprocess_config.get('enabled') else 'stopped',
             stopped_at=utc(), finalized=True, exit_code=0,
             message_count=metadata['message_count'], topic_counts=counts,
             bag_storage={'storage_identifier': metadata['storage_identifier'],
                          'serialization_formats': sorted({entry['topic_metadata']['serialization_format']
                              for entry in metadata['topics_with_message_count']}),
                          'compression_mode': (metadata.get('compression_mode') or 'none').lower(),
                          'compression_format': metadata.get('compression_format') or ''},
             topics_without_messages=[t for t in session['topics'] if not counts.get(t)],
             duration_ns=metadata['duration']['nanoseconds'],
             clock_at_stop=command_output(['timedatectl', 'show', '-p', 'NTPSynchronized', '-p', 'NTP']),
             clock_reference_at_stop=reference_status())
        save(native_finish_reason=native.get('finish_reason'))
        if postprocess_config.get('enabled'):
            from mcap_postprocess import compress_bag
            try:
                result = compress_bag(bag, postprocess_config,
                    progress=lambda **updates: save(mcap_postprocess=dict(status='running', **updates)))
            except Exception as exc:
                # Recording succeeded. A compression error must not erase that
                # fact or retry/delete the valid source behind the user's back.
                result = dict(status='failed', error=str(exc), recording_preserved=True)
            save(status='stopped', mcap_postprocess=result)

    try:
        # This supervisor only exchanges control RPCs and graph metadata. Pinned
        # Humble Zenoh 0.1.11 produced malformed SHM ListParameters replies in
        # the deployed worker; loopback TCP avoids that failure. Sensor and
        # native-recorder endpoints retain the tuned SHM data path.
        if os.environ.get('RMW_IMPLEMENTATION') == 'rmw_zenoh_cpp':
            os.environ['ZENOH_CONFIG_OVERRIDE'] = os.environ.get('ZENOH_CONFIG_OVERRIDE','') + ';transport/shared_memory/enabled=false'
        save(middleware_environment={key:os.environ.get(key) for key in (
            'RMW_IMPLEMENTATION', 'RMW_FASTRTPS_PUBLICATION_MODE', 'ROS_LOCALHOST_ONLY',
            'ZENOH_CONFIG_OVERRIDE', 'RMW_ZENOH_BUFFER_POOL_MAX_SIZE_BYTES',
            'ZENOH_ROUTER_CHECK_ATTEMPTS', 'LD_LIBRARY_PATH', 'PYTHONPATH')})
        recorder_config = load_recorder_config()
        save(bag_recorder_config=recorder_config)
        settings = recorder_config['settings']
        validate_ros_plugins(settings)
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
                    'durability': int(e.qos_profile.durability),
                    'history': int(e.qos_profile.history), 'depth': e.qos_profile.depth} for e in endpoints]
               for t, endpoints in publishers.items()}
        effective_zed = None
        if any(t.startswith('/zed2i/zed_node/') for t in session['topics']):
            from rcl_interfaces.srv import GetParameters, ListParameters
            from rclpy.parameter import parameter_value_to_python
            names = ['depth.depth_mode','depth.depth_stabilization',
                     'general.grab_resolution','general.grab_frame_rate','general.pub_frame_rate',
                     'general.sdk_timestamp_clock','general.pub_resolution','general.pub_downscale_factor',
                     'general.grab_compute_capping_fps','video.publish_raw','video.publish_stereo',
                     'pos_tracking.pos_tracking_mode',
                     'pos_tracking.compute_preference','pos_tracking.imu_fusion',
                     'pos_tracking.area_memory','sensors.sensors_pub_rate',
                     'video.publish_rgb','video.publish_left_right','video.enable_24bit_output',
                     'sensors.sensors_image_sync','depth.publish_depth_map']
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
                    # Plugin parameter prefixes vary by image_transport version.
                    # Preserve the actual JPEG codec/quality used on both cameras.
                    names += sorted(name for name in declared
                                    if '.image.' in name and
                                    name.endswith(('.jpeg_quality', '.format')))
                    selected = [name for name in names if name in declared]
                    future = client.call_async(GetParameters.Request(names=selected))
                    rclpy.spin_until_future_complete(node, future, timeout_sec=3)
                    if future.done() and future.result() is not None:
                        values = future.result().values
                        if len(values) == len(selected):
                            effective_zed = dict(zip(selected, [parameter_value_to_python(v) for v in values]))
                            effective_zed['_undeclared'] = [name for name in names if name not in declared]
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
             ros_domain_id=os.environ.get('ROS_DOMAIN_ID', '0'),
             ros_localhost_only=os.environ.get('ROS_LOCALHOST_ONLY', '0'))
        bag = Path(session['bag_path'])
        if stop_requested:
            save(status='stopped', stopped_at=utc(), finalized=False, message='Cancelled before recording began.')
            return 0
        from musohu_bag_recorder.srv import TriggerBagRecording, StopBagRecording, GetBagRecordingState
        from rclpy.utilities import get_rmw_implementation_identifier
        start_client = node.create_client(TriggerBagRecording, '/musohu/recorder/start')
        stop_client = node.create_client(StopBagRecording, '/musohu/recorder/stop')
        state_client = node.create_client(GetBagRecordingState, '/musohu/recorder/get_state')

        def call(client, request, timeout=5):
            future = client.call_async(request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=timeout)
            if not future.done():
                future.cancel()
                raise RuntimeError('Recorder service did not respond: ' + client.srv_name)
            if future.exception():
                raise RuntimeError('Recorder service failed: ' + str(future.exception()))
            return future.result()

        if not start_client.wait_for_service(timeout_sec=5):
            raise RuntimeError('Recorder service unavailable. Start helmet nodes, or launch the standalone recorder for dummy testing.')
        if stop_requested:
            save(status='stopped', stopped_at=utc(), finalized=False, message='Cancelled before recording began.')
            return 0
        stop_request = StopBagRecording.Request(session_id=session['session_id'])
        request = TriggerBagRecording.Request(
            session_id=session['session_id'], reason='web_or_benchmark',
            bag_uri=str(bag), topics=session['topics'], settings_json=json.dumps(settings),
            context_json=json.dumps(session), owner_timeout_sec=8.0)
        save(recorder_backend='musohu_bag_recorder/rosbag2_cpp',
             recorder_services={'start': start_client.srv_name, 'stop': stop_client.srv_name,
                                'state': state_client.srv_name},
             rmw_implementation=get_rmw_implementation_identifier(),
             cyclone_uri=os.environ.get('CYCLONEDDS_URI'))
        service_attempted = True
        response = call(start_client, request)
        if not response.success:
            raise RuntimeError(response.message)
        if response.bag_uri != str(bag):
            raise RuntimeError('Recorder returned a different bag path')
        deadline = time.monotonic() + 15
        ready = False
        while not stop_requested:
            state = json.loads(call(state_client, GetBagRecordingState.Request(
                session_id=session['session_id'], renew_lease=True)).state_json)
            if state['session_id'] != session['session_id']:
                raise RuntimeError('Native recorder session ownership changed unexpectedly')
            if state['status'] in ('failed', 'stopped'):
                raise RuntimeError(state.get('error') or 'Native recorder stopped unexpectedly')
            if not ready and state['status'] == 'recording' and set(session['topics']).issubset(state['subscribed_topics']):
                ready = True
                save(status='recording', started_at=state['started_at'],
                     recorder_pid=state['recorder_pid'], recorder_settings=state['settings'])
            if not ready and time.monotonic() > deadline:
                raise RuntimeError('Recorder did not confirm subscriptions before startup timeout.')
            time.sleep(0.2)
        save(status='stopping')
        response = call(stop_client, stop_request, timeout=25)
        if not response.success or response.recording or not response.finalized or response.bag_uri != str(bag):
            raise RuntimeError(response.message or 'Native recorder did not confirm finalization')
        service_closed = True
        metadata_path = bag / 'metadata.yaml'
        if not metadata_path.is_file():
            raise RuntimeError('Native recorder reported finalization but bag metadata is missing')
        save_finished()
        return 0
    except Exception as exc:
        # A launched recorder can finish during ROS launch/API shutdown before
        # replying to Stop. Accept only its matching, explicit finalization
        # record plus readable bag metadata; presence of a bag alone is not enough.
        if service_attempted:
            try:
                save_finished()
                service_closed = True
                return 0
            except (OSError, ValueError, KeyError, RuntimeError, TypeError, yaml.YAMLError):
                pass
        save(status='failed', error=str(exc), stopped_at=utc(), finalized=False,
             loaded_middleware_libraries=sorted({line.split()[-1] for line in
                 Path('/proc/self/maps').read_text().splitlines()
                 if any(name in line for name in ('fastcdr', 'fastrtps', 'rmw_', 'zenoh'))}))
        return 1
    finally:
        if service_attempted and not service_closed and node is not None and stop_client is not None:
            try:
                # Stop only this session; the native lease is the final fallback
                # if this worker cannot reach the service or is forcibly killed.
                call(stop_client, stop_request, timeout=25)
            except Exception:
                pass
        if node is not None:
            node.destroy_node()
        if context_started:
            rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())

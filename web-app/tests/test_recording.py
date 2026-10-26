"""Exercise the API with the native C++ recorder and synthetic ROS publishers.

Requires a built workspace and requirements-dev.txt. Uses isolated domain 99;
no helmet devices, deployed service or real recording directories are touched.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import signal
import socket
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app as application
from process_manager import ProcessManager
import httpx


TOPICS = ['/musohu_dummy/imu', '/musohu_dummy/points', '/musohu_dummy/audio_stamped']


class RecordingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        tuning = (';scouting/multicast/enabled=false;transport/shared_memory/enabled=true;'
                  'transport/link/tx/queue/congestion_control/drop/wait_before_drop=1000000')
        cls.environment = patch.dict(os.environ, {'ROS_DOMAIN_ID': '99', 'ROS_LOCALHOST_ONLY': '1',
            'RMW_IMPLEMENTATION': 'rmw_zenoh_cpp',
            'ZENOH_CONFIG_OVERRIDE':f'connect/endpoints=["tcp/127.0.0.1:{port}"];listen/endpoints=["tcp/127.0.0.1:0"]'+tuning})
        cls.environment.start()
        manager = ProcessManager(application.BASE_DIR, {})
        router_env = dict(os.environ, ZENOH_CONFIG_OVERRIDE=
            f'listen/endpoints=["tcp/127.0.0.1:{port}"];connect/endpoints=[]'+tuning)
        cls.router = subprocess.Popen(manager.ros_command([
            '/opt/ros/humble/lib/rmw_zenoh_cpp/rmw_zenohd']), env=router_env,
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.1): break
            except OSError: time.sleep(.1)
        else:
            os.killpg(cls.router.pid, signal.SIGINT)
            cls.router.wait(timeout=10)
            cls.environment.stop()
            raise RuntimeError('Test Zenoh router failed to start')
        script = manager.workspace / 'scripts/dummy-sensors.py'
        cls.dummy = subprocess.Popen(manager.ros_command(['/usr/bin/python3', str(script)]),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                                     start_new_session=True)

    @classmethod
    def tearDownClass(cls):
        os.killpg(cls.dummy.pid, signal.SIGINT)
        cls.dummy.wait(timeout=10)
        os.killpg(cls.router.pid, signal.SIGINT)
        cls.router.wait(timeout=10)
        cls.environment.stop()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'MUSOHU_BAG_DIR': self.directory.name})
        self.env.start()
        self.original = application.manager
        self.manager = ProcessManager(application.BASE_DIR, {
            'ros': {'process_log_directory': self.directory.name + '/logs'}})
        # Recording ownership tests are independent of this host's current
        # offline/online clock reference; clock guards have separate coverage.
        self.clock_guard = patch.object(self.manager, 'require_clock_reference')
        self.clock_guard.start()
        application.manager = self.manager
        with open(Path(self.directory.name) / 'native-recorder.log', 'w') as log:
            self.native_recorder = subprocess.Popen(self.manager.ros_command([
                'ros2', 'run', 'musohu_bag_recorder', 'bag_recorder_node', '--ros-args',
                '-p', 'output_directory:=' + self.directory.name]),
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.client = TestClient(application.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        if self.native_recorder.poll() is None:
            os.killpg(self.native_recorder.pid, signal.SIGINT)
        self.native_recorder.wait(timeout=15)
        application.manager = self.original
        self.clock_guard.stop()
        self.env.stop()
        self.directory.cleanup()

    def state(self):
        return self.client.get('/api/scripts').json()['record_bag']

    def wait_for(self, states, timeout=20, settled=False):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.state()
            if state['status'] in states and (not settled or state.get('pid') is None):
                return state
            time.sleep(0.1)
        self.fail(f'Timed out waiting for {states}: {self.state()}')

    def start(self, label='test', topics=None):
        return self.client.post('/api/scripts/record_bag/start',
                                json={'label': label, 'topics': TOPICS if topics is None else topics})

    def test_ros_children_escape_web_virtualenv(self):
        # Match systemd's API venv PATH and site restriction. ROS scripts with
        # /usr/bin/env python3 shebangs must still import native sensor deps.
        venv = Path(application.BASE_DIR) / 'venv'
        code = ('import json,os,sys,rclpy,numpy,tf_transformations,pixel_ring; '
                'print(json.dumps(dict(python=sys.executable, '
                'venv=os.getenv("VIRTUAL_ENV"), no_user_site=os.getenv("PYTHONNOUSERSITE"), '
                'localhost=os.getenv("ROS_LOCALHOST_ONLY"), '
                'rmw=os.getenv("RMW_IMPLEMENTATION"), '
                'publication=os.getenv("RMW_FASTRTPS_PUBLICATION_MODE"))))')
        with patch.dict(os.environ, {'PATH': str(venv / 'bin') + ':' + os.environ['PATH'],
                                    'VIRTUAL_ENV': str(venv), 'PYTHONNOUSERSITE': '1',
                                    'ROS_LOCALHOST_ONLY': '0', 'RMW_FASTRTPS_PUBLICATION_MODE': '',
                                    'RMW_IMPLEMENTATION': ''}):
            state = json.loads(subprocess.check_output(
                self.manager.ros_command(['python3', '-c', code]), text=True))
        self.assertEqual(state['python'], '/usr/bin/python3')
        self.assertIsNone(state['venv'])
        self.assertIsNone(state['no_user_site'])
        self.assertEqual(state['localhost'], '1')
        self.assertEqual(state['publication'], 'ASYNCHRONOUS')
        self.assertEqual(state['rmw'], 'rmw_zenoh_cpp')
        with patch.dict(os.environ, {'RMW_FASTRTPS_PUBLICATION_MODE':'SYNCHRONOUS',
                                    'RMW_IMPLEMENTATION':'rmw_fastrtps_cpp'}):
            explicit=json.loads(subprocess.check_output(
                self.manager.ros_command(['python3','-c',code]),text=True))
        self.assertEqual(explicit['publication'],'SYNCHRONOUS')
        self.assertEqual(explicit['rmw'],'rmw_fastrtps_cpp')

    def test_depthless_zed_metadata_ignores_undeclared_parameters(self):
        # Match the depthless wrapper: depth_stabilization is not declared.
        code = '''import rclpy
from sensor_msgs.msg import Imu
rclpy.init()
n=rclpy.create_node('zed_node',namespace='/zed2i')
n.declare_parameter('depth.depth_mode','NONE')
n.declare_parameter('pos_tracking.pos_tracking_mode','GEN_3')
n.declare_parameter('video.publish_left_right',True)
n.declare_parameter('video.enable_24bit_output',True)
n.declare_parameter('sensors.sensors_image_sync',False)
p=n.create_publisher(Imu,'~/imu/data',10)
def publish():
 m=Imu();m.header.stamp=n.get_clock().now().to_msg();p.publish(m)
n.create_timer(.05,publish)
try:rclpy.spin(n)
except KeyboardInterrupt:pass
finally:n.destroy_node();rclpy.try_shutdown()
'''
        publisher = subprocess.Popen(self.manager.ros_command(['/usr/bin/python3','-c',code]),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        try:
            response = self.start('depthless_metadata', ['/zed2i/zed_node/imu/data'])
            self.assertEqual(response.status_code, 202)
            state = self.wait_for({'recording','failed'})
            self.assertEqual(state['status'], 'recording', state.get('error'))
            time.sleep(.3)
            final = self.client.post('/api/scripts/record_bag/stop').json()
            self.assertTrue(final['finalized'])
            self.assertEqual(final['rmw_implementation'], 'rmw_zenoh_cpp')
            self.assertIn('transport/shared_memory/enabled=false',
                          final['middleware_environment']['ZENOH_CONFIG_OVERRIDE'])
            effective = final['zed_effective_parameters']
            self.assertEqual(effective['depth.depth_mode'], 'NONE')
            self.assertEqual(effective['pos_tracking.pos_tracking_mode'], 'GEN_3')
            self.assertTrue(effective['video.publish_left_right'])
            self.assertTrue(effective['video.enable_24bit_output'])
            self.assertFalse(effective['sensors.sensors_image_sync'])
            self.assertIn('depth.depth_stabilization', effective['_undeclared'])
        finally:
            os.killpg(publisher.pid, signal.SIGINT)
            publisher.wait(timeout=10)

    def test_record_flush_and_restart(self):
        bags = []
        for label in ('first', 'second'):
            response = self.start(label)
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()['status'], 'starting')
            state = self.wait_for({'recording', 'failed'})
            self.assertEqual(state['status'], 'recording', state.get('error'))
            time.sleep(0.4)
            response = self.client.post('/api/scripts/record_bag/stop')
            self.assertEqual(response.status_code, 200)
            state = response.json()
            self.assertTrue(state['finalized'])
            self.assertEqual(state['ros_localhost_only'], '1')
            self.assertGreater(state['message_count'], 0)
            self.assertTrue(all(state['topic_counts'].get(topic, 0) for topic in TOPICS))
            self.assertTrue((Path(state['bag_path']) / 'metadata.yaml').is_file())
            bags.append(state['bag_path'])
        self.assertNotEqual(*bags)

    def test_recorder_config_reloads_between_sessions(self):
        config_path = Path(self.directory.name) / 'bag_recorder_config.yml'
        with patch.dict(os.environ, {'MUSOHU_BAG_RECORDER_CONFIG': str(config_path)}):
            for cache_size in (1048576, 0):
                config_path.write_text(yaml.safe_dump({'max_cache_size': cache_size}))
                self.assertEqual(self.start('configured_cache').status_code, 202)
                state = self.wait_for({'recording', 'failed'})
                self.assertEqual(state['status'], 'recording', state.get('error'))
                command = Path(f"/proc/{state['recorder_pid']}/cmdline").read_bytes().decode()
                self.assertIn('bag_recorder_node', command)
                self.assertEqual(state['recorder_backend'], 'musohu_bag_recorder/rosbag2_cpp')
                self.assertEqual(state['recorder_settings']['max_cache_size'], cache_size)
                self.assertEqual(state['bag_recorder_config']['settings']['max_cache_size'], cache_size)
                # An active recorder keeps its snapshot even if the YAML changes.
                config_path.write_text('max_cache_size: 524288\n')
                time.sleep(.4)
                final = self.client.post('/api/scripts/record_bag/stop').json()
                self.assertTrue(final['finalized'], final.get('error'))
                native = json.loads((Path(final['bag_path']) / 'recording_metadata.json').read_text())
                self.assertEqual(native['settings']['max_cache_size'], cache_size)
                self.assertEqual(native['session_id'], final['session_id'])
                self.assertEqual(final['bag_recorder_config']['settings']['max_cache_size'], cache_size)
                self.assertEqual(final['bag_storage']['storage_identifier'], 'mcap')
                self.assertEqual(final['bag_storage']['serialization_formats'], ['cdr'])
                self.assertEqual(final['bag_storage']['compression_mode'], 'none')
                self.assertTrue(all(final['topic_counts'].get(topic, 0) for topic in TOPICS))

    def test_postprocess_zstd_is_asynchronous_and_verified(self):
        wrapper = Path(self.directory.name)/'slow-mcap'
        wrapper.write_text('#!/usr/bin/python3\nimport os,sys,time\n'
                           'if "compress" in sys.argv: time.sleep(3)\n'
                           'os.execv("/usr/local/bin/mcap",["mcap",*sys.argv[1:]])\n')
        wrapper.chmod(0o755)
        self.manager.postprocess_config = {'enabled':True, 'executable':str(wrapper)}
        self.manager.stop_timeout = 2
        self.assertEqual(self.start('postprocess').status_code, 202)
        self.assertEqual(self.wait_for({'recording','failed'})['status'], 'recording')
        time.sleep(.3)
        response = self.client.post('/api/scripts/record_bag/stop')
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()['status'], 'compressing')
        self.assertTrue(response.json()['finalized'])
        self.assertEqual(self.start('too_early').status_code, 400)
        final = self.wait_for({'stopped','failed'}, settled=True)
        self.assertEqual(final['status'], 'stopped', final)
        result = final['mcap_postprocess']
        self.assertEqual(result['status'], 'completed', result)
        self.assertTrue(result['files'][0]['verified'])
        self.assertEqual(result['files'][0]['message_counts'], final['topic_counts'])
        self.assertLess(result['compressed_bytes'], result['original_bytes'])
        self.assertEqual(len(list(Path(final['bag_path']).glob('*.mcap'))), 1)
        subprocess.run(['/usr/local/bin/mcap','doctor',
            str(next(Path(final['bag_path']).glob('*.mcap')))], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_postprocess_corrupt_output_retains_original(self):
        wrapper = Path(self.directory.name)/'corrupt-mcap'
        wrapper.write_text('''#!/usr/bin/python3
import hashlib,os,sys
from pathlib import Path
if 'compress' in sys.argv:
 source=Path(sys.argv[2]); source.with_suffix('.sha256').write_text(hashlib.sha256(source.read_bytes()).hexdigest())
 Path(sys.argv[sys.argv.index('--output')+1]).write_bytes(b'corrupt')
else: os.execv('/usr/local/bin/mcap',['mcap',*sys.argv[1:]])
''')
        wrapper.chmod(0o755)
        self.manager.postprocess_config = {'enabled':True, 'executable':str(wrapper)}
        self.assertEqual(self.start('corrupt_postprocess').status_code, 202)
        self.assertEqual(self.wait_for({'recording','failed'})['status'], 'recording')
        time.sleep(.3)
        self.client.post('/api/scripts/record_bag/stop')
        final = self.wait_for({'stopped','failed'}, settled=True)
        self.assertTrue(final['finalized'])
        self.assertEqual(final['mcap_postprocess']['status'], 'failed')
        bag = Path(final['bag_path']); source = next(bag.glob('*.mcap'))
        import hashlib
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         source.with_suffix('.sha256').read_text())
        self.assertFalse(list(bag.glob('.*.zstd-*.mcap')))

    def test_zstd_compression_records_and_replays(self):
        config_path = Path(self.directory.name) / 'bag_recorder_config.yml'
        # Decode the finished compressed bag, rather than only trusting CLI args.
        code = '''import json,sys,rosbag2_py
r=rosbag2_py.SequentialCompressionReader()
r.open(rosbag2_py.StorageOptions(uri=sys.argv[1],storage_id='sqlite3'),
       rosbag2_py.ConverterOptions(input_serialization_format='cdr',output_serialization_format='cdr'))
counts={}
while r.has_next():
 topic,data,stamp=r.read_next();counts[topic]=counts.get(topic,0)+1
del r
print(json.dumps(counts))
'''
        with patch.dict(os.environ, {'MUSOHU_BAG_RECORDER_CONFIG': str(config_path)}):
            for mode in ('file', 'message'):
                with self.subTest(mode=mode):
                    config_path.write_text(f'storage: sqlite3\nmax_cache_size: 1048576\ncompression_mode: {mode}\n'
                                           'compression_format: zstd\ncompression_threads: 1\n')
                    self.assertEqual(self.start('configured_zstd').status_code, 202)
                    state = self.wait_for({'recording', 'failed'})
                    self.assertEqual(state['status'], 'recording', state.get('error'))
                    time.sleep(.5)
                    final = self.client.post('/api/scripts/record_bag/stop').json()
                    self.assertTrue(final['finalized'], final.get('error'))
                    self.assertEqual(final['bag_storage']['compression_mode'], mode)
                    self.assertEqual(final['bag_storage']['compression_format'], 'zstd')
                    suffix = '*.db3.zstd' if mode == 'file' else '*.db3'
                    self.assertTrue(list(Path(final['bag_path']).glob(suffix)))
                    result = subprocess.check_output(self.manager.ros_command(
                        ['/usr/bin/python3', '-c', code, final['bag_path']]), text=True)
                    counts = json.loads(result.strip().splitlines()[-1])
                    self.assertEqual(counts, final['topic_counts'])

    def test_bad_recorder_config_fails_without_creating_bag(self):
        config_path = Path(self.directory.name) / 'bag_recorder_config.yml'
        with patch.dict(os.environ, {'MUSOHU_BAG_RECORDER_CONFIG': str(config_path)}):
            for text, error in [('max_cache_size: -1', 'max_cache_size'),
                                ('storage: missing_musohu_plugin', 'not installed'),
                                ('compression_mode: file\ncompression_format: missing_musohu_codec', 'not installed'),
                                ('serialization_format: missing_musohu_converter', 'not installed')]:
                with self.subTest(config=text):
                    config_path.write_text(text)
                    self.assertEqual(self.start('invalid_config').status_code, 202)
                    state = self.wait_for({'failed'}, settled=True)
                    self.assertIn(error, state['error'])
                    self.assertFalse(Path(state['bag_path']).exists())

    def test_concurrent_start_has_one_owner(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: self.start(), range(4)))
        self.assertEqual(sum(r.status_code == 202 for r in responses), 1)
        self.assertEqual(sum(r.status_code == 400 for r in responses), 3)
        self.client.post('/api/scripts/record_bag/stop')

    def test_restart_waits_for_stop_cleanup(self):
        self.start()
        self.assertEqual(self.wait_for({'recording', 'failed'})['status'], 'recording')
        process = self.manager.processes['record_bag']
        original_wait = process.wait
        finished, release = threading.Event(), threading.Event()

        def wait_before_cleanup(*args, **kwargs):
            result = original_wait(*args, **kwargs)
            finished.set()
            if not release.wait(timeout=10):
                raise RuntimeError('Test did not release stop cleanup')
            return result

        with patch.object(process, 'wait', side_effect=wait_before_cleanup):
            with ThreadPoolExecutor(max_workers=1) as pool:
                stopped = pool.submit(self.manager.stop, 'record_bag')
                try:
                    self.assertTrue(finished.wait(timeout=15))
                    # Polling may already reap the old worker. A new request
                    # must still wait for its in-flight Stop to finish.
                    self.assertEqual(self.start('too_early').status_code, 400)
                finally:
                    release.set()
                self.assertTrue(stopped.result(timeout=10)['finalized'])

    def test_missing_topic_is_failure_not_running(self):
        self.assertEqual(self.start(topics=['/no_such_musohu_topic']).status_code, 202)
        state = self.wait_for({'failed'}, settled=True)
        self.assertIn('No publisher', state['error'])
        self.assertIsNone(state['pid'])
        self.assertFalse(Path(state['bag_path']).exists())

    def test_invalid_input_never_starts(self):
        for topics in ([], ['/valid;touch /tmp/bad'], ['relative_topic']):
            self.assertEqual(self.start(topics=topics).status_code, 400)
        self.assertEqual(self.start(label='../escape').status_code, 400)
        self.assertEqual(self.state()['status'], 'stopped')

    def test_stop_during_preflight(self):
        self.assertEqual(self.start(topics=['/not_present']).status_code, 202)
        response = self.client.post('/api/scripts/record_bag/stop')
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(response.json()['status'], 'stopped')
        self.assertIsNone(self.state()['pid'])

    def test_worker_crash_is_reported(self):
        self.start()
        state = self.wait_for({'recording', 'failed'})
        self.assertEqual(state['status'], 'recording', state.get('error'))
        os.kill(state['pid'], signal.SIGKILL)
        state = self.wait_for({'failed'})
        self.assertIsNone(state['pid'])
        self.assertIn('finalization', state['error'])
        # SIGKILL cannot reach Python cleanup. The C++ owner's steady-clock
        # lease must still close the bag rather than record indefinitely.
        metadata = Path(state['bag_path']) / 'metadata.yaml'
        native_path = Path(state['bag_path']) / 'recording_metadata.json'
        deadline = time.monotonic() + 15
        native = {}
        while time.monotonic() < deadline:
            if native_path.exists():
                native = json.loads(native_path.read_text())
            if metadata.is_file() and native.get('finalized'):
                break
            time.sleep(.1)
        self.assertTrue(metadata.is_file())
        self.assertEqual(native['finish_reason'], 'owner_lease_expired')
        self.assertTrue(native['finalized'])

    def native_call(self, service_type, service_name, fields):
        code = '''import json,sys,rclpy
from musohu_bag_recorder import srv
from rosidl_runtime_py.convert import message_to_ordereddict
rclpy.init();n=rclpy.create_node('recorder_contract_test')
t=getattr(srv,sys.argv[1]);c=n.create_client(t,sys.argv[2])
assert c.wait_for_service(timeout_sec=5)
f=c.call_async(t.Request(**json.loads(sys.argv[3])))
rclpy.spin_until_future_complete(n,f,timeout_sec=10)
assert f.done()
print(json.dumps(message_to_ordereddict(f.result())))
n.destroy_node();rclpy.shutdown()
'''
        value = subprocess.check_output(self.manager.ros_command([
            '/usr/bin/python3', '-c', code, service_type, service_name, json.dumps(fields)]), text=True)
        return json.loads(value.strip().splitlines()[-1])

    def test_native_owner_and_idempotent_start(self):
        self.start()
        state = self.wait_for({'recording', 'failed'})
        self.assertEqual(state['status'], 'recording', state.get('error'))
        same = self.native_call('TriggerBagRecording', '/musohu/recorder/start',
                                {'session_id': state['session_id'], 'reason': 'repeat'})
        self.assertTrue(same['success'])
        self.assertFalse(same['started_new_bag'])
        self.assertEqual(same['bag_uri'], state['bag_path'])
        foreign = self.native_call('TriggerBagRecording', '/musohu/recorder/start',
                                   {'session_id': 'another_owner', 'reason': 'wrong_owner'})
        self.assertFalse(foreign['success'])
        stopped = self.native_call('StopBagRecording', '/musohu/recorder/stop',
                                   {'session_id': 'another_owner'})
        self.assertFalse(stopped['success'])
        self.assertTrue(stopped['recording'])
        self.assertEqual(self.state()['status'], 'recording')

    def test_missing_native_service_is_clear_failure(self):
        os.killpg(self.native_recorder.pid, signal.SIGINT)
        self.native_recorder.wait(timeout=15)
        self.start()
        state = self.wait_for({'failed'}, settled=True)
        self.assertIn('Recorder service unavailable', state['error'])
        self.assertFalse(Path(state['bag_path']).exists())

    def test_native_direct_start_loads_canonical_yaml(self):
        response = self.native_call('TriggerBagRecording', '/musohu/recorder/start',
                                    {'session_id': 'direct_config', 'reason': 'manual', 'topics': TOPICS})
        self.assertTrue(response['success'], response['message'])
        time.sleep(.3)
        stopped = self.native_call('StopBagRecording', '/musohu/recorder/stop',
                                   {'session_id': 'direct_config'})
        self.assertTrue(stopped['success'], stopped['message'])
        native = json.loads((Path(response['bag_uri']) / 'recording_metadata.json').read_text())
        self.assertEqual(native['settings']['max_cache_size'], 500000000)
        self.assertEqual(native['settings']['storage'], 'mcap')
        self.assertTrue(native['finalized'])

    def test_native_shutdown_confirms_finalization_without_service_reply(self):
        self.start()
        state = self.wait_for({'recording', 'failed'})
        self.assertEqual(state['status'], 'recording', state.get('error'))
        time.sleep(.3)
        os.killpg(self.native_recorder.pid, signal.SIGINT)
        self.native_recorder.wait(timeout=15)
        final = self.wait_for({'stopped', 'failed'}, settled=True)
        self.assertEqual(final['status'], 'stopped', final.get('error'))
        self.assertTrue(final['finalized'])
        self.assertEqual(final['native_finish_reason'], 'node_shutdown')

    def test_api_death_finalizes_recording(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        with open(Path(self.directory.name) / 'api.log', 'w') as log:
            server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app:app',
                                       '--app-dir', application.BASE_DIR, '--port', str(port)],
                                      stdout=log, stderr=subprocess.STDOUT)
            try:
                client = httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=5)
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    try:
                        if client.get('/api/health').status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                response = client.post('/api/scripts/record_bag/start', json={'label': 'parent_death', 'topics': TOPICS})
                self.assertEqual(response.status_code, 202)
                state = response.json()
                deadline = time.monotonic() + 20
                while state['status'] == 'starting' and time.monotonic() < deadline:
                    time.sleep(0.1)
                    state = client.get('/api/scripts').json()['record_bag']
                self.assertEqual(state['status'], 'recording', state.get('error'))
                time.sleep(0.3)
                server.kill()
                server.wait(timeout=5)
                metadata = Path(state['bag_path'] + '.session.json')
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    final = json.loads(metadata.read_text())
                    if final['status'] in ('stopped', 'failed'):
                        break
                    time.sleep(0.1)
                self.assertEqual(final['status'], 'stopped', final.get('error'))
                self.assertTrue(final['finalized'])
                self.assertGreater(final['message_count'], 0)
                client.close()
            finally:
                if server.poll() is None:
                    server.terminate()
                    server.wait(timeout=10)


if __name__ == '__main__':
    unittest.main()

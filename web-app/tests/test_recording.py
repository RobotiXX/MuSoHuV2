"""Exercise the API with real rosbag processes and synthetic ROS publishers.

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app as application
from process_manager import ProcessManager
import httpx


TOPICS = ['/musohu_dummy/imu', '/musohu_dummy/points', '/musohu_dummy/audio_stamped']


class RecordingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ, {'ROS_DOMAIN_ID': '99', 'ROS_LOCALHOST_ONLY': '1'})
        cls.environment.start()
        manager = ProcessManager(application.BASE_DIR, {})
        script = manager.workspace / 'scripts/dummy-sensors.py'
        cls.dummy = subprocess.Popen(manager.ros_command(['/usr/bin/python3', str(script)]),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                                     start_new_session=True)

    @classmethod
    def tearDownClass(cls):
        os.killpg(cls.dummy.pid, signal.SIGINT)
        cls.dummy.wait(timeout=10)
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
        self.client = TestClient(application.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
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

    def test_depthless_zed_metadata_ignores_undeclared_parameters(self):
        # Match the depthless wrapper: depth_stabilization is not declared.
        code = '''import rclpy
from sensor_msgs.msg import Imu
rclpy.init()
n=rclpy.create_node('zed_node',namespace='/zed2i')
n.declare_parameter('depth.depth_mode','NONE')
n.declare_parameter('pos_tracking.pos_tracking_mode','GEN_3')
n.declare_parameter('video.publish_left_right',True)
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
            effective = final['zed_effective_parameters']
            self.assertEqual(effective['depth.depth_mode'], 'NONE')
            self.assertEqual(effective['pos_tracking.pos_tracking_mode'], 'GEN_3')
            self.assertTrue(effective['video.publish_left_right'])
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
            self.assertGreater(state['message_count'], 0)
            self.assertTrue(all(state['topic_counts'].get(topic, 0) for topic in TOPICS))
            self.assertTrue((Path(state['bag_path']) / 'metadata.yaml').is_file())
            bags.append(state['bag_path'])
        self.assertNotEqual(*bags)

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

"""Run the real monitor against synthetic streams, then degrade and stop one.

Source Humble and the built workspace. Domain 107 and temporary state files
keep this test separate from helmet hardware and the deployed web app.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

import rclpy
from audio_common_msgs.msg import AudioDataStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu


class MonitorRosTest(unittest.TestCase):
    def test_real_rates_degradation_missing_and_diagnostics(self):
        env = dict(os.environ, ROS_DOMAIN_ID='107', ROS_LOCALHOST_ONLY='1')
        # The global executor used by spin_once must share the initialized context.
        rclpy.init(domain_id=107)
        node = rclpy.create_node('synthetic_health_sensors')
        publishers = [node.create_publisher(cls, topic, 100) for cls, topic in [
            (Imu, '/witmotion_imu/imu'), (Odometry, '/zed2i/zed_node/odom'),
            (AudioDataStamped, '/audio_stamped')]]
        from diagnostic_msgs.msg import DiagnosticArray
        diagnostics = []
        subscription = node.create_subscription(DiagnosticArray, '/diagnostics',
                                               diagnostics.append, 10)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'state.json'
            with (Path(directory)/'monitor.log').open('w') as log:
                process = subprocess.Popen(['ros2','run','helmet_bringup','sensor_health_monitor.py',
                    '--ros-args','-p','state_file:='+str(path),'-p','window_s:=2.0',
                    '-p','warmup_s:=1.0','-p','stale_s:=0.5','-p','report_period_s:=0.2'],
                    env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                periods=[1/200,1/30,1/15.625]
                next_due=[time.monotonic()]*3
                def wait_for(status, timeout=8):
                    deadline=time.monotonic()+timeout
                    while time.monotonic()<deadline:
                        now=time.monotonic()
                        for i, cls in enumerate([Imu,Odometry,AudioDataStamped]):
                            if periods[i] is not None and now>=next_due[i]:
                                publishers[i].publish(cls())
                                next_due[i]=max(next_due[i]+periods[i],now)
                        rclpy.spin_once(node,timeout_sec=.001)
                        if path.exists():
                            state=json.loads(path.read_text())
                            if state['sensors']['witmotion']['status']==status:
                                return state
                        self.assertIsNone(process.poll(), 'Monitor exited; inspect '+str(log.name))
                    self.fail('Timed out waiting for '+status)
                try:
                    healthy=wait_for('healthy')
                    self.assertTrue(healthy['sensors']['zed']['healthy'])
                    self.assertTrue(healthy['sensors']['audio']['healthy'])
                    self.assertEqual(healthy['sensors']['lidar']['status'],'not_monitored')
                    periods[0]=.05  # 20 Hz rather than the required 200 Hz.
                    self.assertFalse(wait_for('unhealthy')['sensors']['witmotion']['healthy'])
                    periods[0]=None
                    self.assertFalse(wait_for('missing')['sensors']['witmotion']['healthy'])
                    self.assertTrue(any(any(s.name=='MuSoHu sensors/witmotion'
                                            for s in message.status) for message in diagnostics))
                finally:
                    if process.poll() is None:os.killpg(process.pid,signal.SIGINT)
                    process.wait(timeout=10)
                    node.destroy_node();rclpy.shutdown()


if __name__=='__main__':unittest.main()

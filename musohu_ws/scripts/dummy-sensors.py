#!/usr/bin/env python3
"""Publish synthetic ROS sensor messages for web/recording development.

Default namespace /musohu_dummy avoids real rig topics. These messages are
test fixtures and must not be used to evaluate sensor quality or odometry.
"""
import argparse
import math
import signal
import struct


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--namespace', default='/musohu_dummy')
    parser.add_argument('--rate', type=float, default=10)
    args = parser.parse_args()
    if not math.isfinite(args.rate) or not 1 <= args.rate <= 100:
        parser.error('Rate must be between 1 and 100 Hz.')
    import rclpy
    from rclpy.signals import SignalHandlerOptions
    from sensor_msgs.msg import Imu, PointCloud2, PointField
    from nav_msgs.msg import Odometry
    from audio_common_msgs.msg import AudioData, AudioDataStamped
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node('dummy_sensors', namespace=args.namespace)
    publishers = {name: node.create_publisher(typ, name, 10) for name, typ in [
        ('imu', Imu), ('points', PointCloud2), ('odom', Odometry), ('audio_stamped', AudioDataStamped)]}
    count = 0
    def publish():
        nonlocal count
        stamp = node.get_clock().now().to_msg()
        imu = Imu()
        imu.header.stamp = stamp
        imu.header.frame_id = 'dummy_imu'
        imu.orientation.w = 1.0
        imu.linear_acceleration.z = 9.80665
        publishers['imu'].publish(imu)
        cloud = PointCloud2()
        cloud.header.stamp = stamp
        cloud.header.frame_id = 'dummy_lidar'
        cloud.height, cloud.width, cloud.point_step, cloud.row_step = 1, 8, 26, 208
        cloud.is_dense = True
        cloud.fields = [PointField(name=name, offset=offset, datatype=typ, count=1)
                        for name, offset, typ in [('x',0,7),('y',4,7),('z',8,7),
                                                   ('intensity',12,7),('ring',16,4),('timestamp',18,8)]]
        seconds = stamp.sec + stamp.nanosec * 1e-9
        cloud.data = b''.join(struct.pack('<ffffHd', float(i),0.0,0.0,1.0,i,seconds) for i in range(8))
        publishers['points'].publish(cloud)
        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = 'dummy_odom'
        odom.child_frame_id = 'dummy_base'
        odom.pose.pose.orientation.w = 1.0
        odom.pose.pose.position.x = count * 0.001
        publishers['odom'].publish(odom)
        audio = AudioDataStamped()
        audio.header.stamp = stamp
        audio.header.frame_id = 'dummy_microphone'
        audio.audio = AudioData(data=struct.pack('<' + 'h' * round(16000 / args.rate),
            *(round(1000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(round(16000 / args.rate)))))
        publishers['audio_stamped'].publish(audio)
        count += 1
    node.create_timer(1.0 / args.rate, publish)
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    print('Synthetic topics: ' + ', '.join(args.namespace.rstrip('/') + '/' + name for name in publishers), flush=True)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
import math
from math import pi

import numpy as np

import rclpy
from rclpy.node import Node

from tf_transformations import euler_from_quaternion
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist, Vector3


class TwistManager(Node):
    def __init__(self):
        super().__init__('action_generator')

        # publisher & subscriber
        self.action_pub = self.create_publisher(Odometry, "/action", 10)
        self.subscription = self.create_subscription(
            Odometry,
            "/zed2i/zed_node/odom",
            self.listen,
            10
        )

        # state
        self.last_odom = None
        self.last_angle_z = 0.0
        self.prev_time = None  # ns
        self.vx = 0.0
        self.vy = 0.0
        self.wz = 0.0

    def listen(self, data: Odometry):
        # current time from header (ns)
        curr_time = data.header.stamp.sec * 1000000000 + data.header.stamp.nanosec

        # initialize on first message
        if self.last_odom is None or self.prev_time is None:
            self.last_odom = data
            q = data.pose.pose.orientation
            current_euler_xyz = euler_from_quaternion([q.x, q.y, q.z, q.w])
            self.last_angle_z = current_euler_xyz[2]
            self.prev_time = curr_time
            return

        dt = (curr_time - self.prev_time) / 1000000000.0  # ns -> s

        q = data.pose.pose.orientation
        current_euler_xyz = euler_from_quaternion([q.x, q.y, q.z, q.w])
        current_angle_z = current_euler_xyz[2]

        # transform positions into last frame
        rotation_last_to_world = np.array([
            [math.cos(self.last_angle_z), -math.sin(self.last_angle_z), self.last_odom.pose.pose.position.x],
            [math.sin(self.last_angle_z),  math.cos(self.last_angle_z), self.last_odom.pose.pose.position.y],
            [0.0,                          0.0,                          1.0]
        ])
        rotation_world_to_last = np.linalg.inv(rotation_last_to_world)

        current_pos_in_world_frame = np.matrix([
            [data.pose.pose.position.x],
            [data.pose.pose.position.y],
            [1.0]
        ])
        current_pos_in_last_frame = rotation_world_to_last @ current_pos_in_world_frame

        delta_z = current_angle_z - self.last_angle_z

        # wrap angle to [-pi, pi]
        if delta_z < -pi:
            delta_z += 2 * pi
        if delta_z > pi:
            delta_z -= 2 * pi

        if dt != 0.0:
            # matrix -> scalar
            self.vx = float(current_pos_in_last_frame[0, 0]) / dt
            self.vy = float(current_pos_in_last_frame[1, 0]) / dt
            self.wz = delta_z / dt

        self.update(current_angle_z, curr_time, data)
        self.publish(data)

    def update(self, z, t, data):
        self.prev_time = t
        self.last_odom = data
        self.last_angle_z = z

    def publish(self, curr_odom):
        odom = Odometry()
        odom.header.stamp = curr_odom.header.stamp
        odom.header.frame_id = "action"

        # Fill the twist fields directly
        odom.twist.twist.linear.x = float(self.vx)
        odom.twist.twist.linear.y = float(self.vy)
        odom.twist.twist.linear.z = 0.0

        odom.twist.twist.angular.x = 0.0
        odom.twist.twist.angular.y = 0.0
        odom.twist.twist.angular.z = float(self.wz)

        self.action_pub.publish(odom)


def main(args=None):
    rclpy.init(args=args)
    node = TwistManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

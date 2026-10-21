"""Publish the finalized sensor extrinsics beneath the ZED tracking frame."""
from pathlib import Path

import yaml
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def publish_transforms(context):
    config_path = LaunchConfiguration('extrinsics_file').perform(context)
    config = yaml.safe_load(Path(config_path).read_text())
    nodes = []
    for child, transform in config['transforms'].items():
        arguments = ['--frame-id', config['parent_frame'], '--child-frame-id', child]
        values = transform['translation'] + transform['rotation_xyzw']
        for flag, value in zip(('--x', '--y', '--z', '--qx', '--qy', '--qz', '--qw'), values):
            arguments.extend((flag, str(value)))
        nodes.append(Node(
            package='tf2_ros', executable='static_transform_publisher',
            name='helmet_static_' + child, arguments=arguments, output='screen',
        ))
    return nodes


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('extrinsics_file', default_value=PathJoinSubstitution([
            FindPackageShare('helmet_bringup'), 'config', 'sensor_extrinsics.yaml',
        ])),
        OpaqueFunction(function=publish_transforms),
    ])

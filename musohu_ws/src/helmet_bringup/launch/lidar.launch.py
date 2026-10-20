"""Launch Helios using the RoboSense native YAML configuration schema."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_prefix
from pathlib import Path
import subprocess


def checked_node(context):
    config = LaunchConfiguration('config_path').perform(context)
    checker = Path(get_package_prefix('helmet_bringup')) / 'lib/helmet_bringup/check_lidar_clock.py'
    subprocess.run(['/usr/bin/python3', str(checker), '--config', config], check=True, timeout=6)
    return [Node(package='rslidar_sdk', executable='rslidar_sdk_node', output='screen',
                 parameters=[{'config_path': config}]),
            Node(package='helmet_bringup', executable='time_sync_monitor.py',
                 arguments=['--config', config], output='screen')]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('config_path', default_value=PathJoinSubstitution([
            FindPackageShare('helmet_bringup'), 'config', 'lidar_params.yaml',
        ])),
        OpaqueFunction(function=checked_node),
    ])

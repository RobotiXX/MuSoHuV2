"""Standalone service recorder, also included by helmet bringup."""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('bag_directory', default_value=os.environ.get(
            'MUSOHU_BAG_DIR', os.path.expanduser('~/helmet_bags'))),
        DeclareLaunchArgument('bag_recorder_config', default_value=PathJoinSubstitution([
            FindPackageShare('musohu_bag_recorder'), 'config', 'bag_recorder_config.yml'])),
        Node(package='musohu_bag_recorder', executable='bag_recorder_node',
             name='musohu_bag_recorder', output='screen', parameters=[{
                 'output_directory': LaunchConfiguration('bag_directory'),
                 'config_file': LaunchConfiguration('bag_recorder_config')}]),
    ])

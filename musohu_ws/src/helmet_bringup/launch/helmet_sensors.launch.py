"""Bring up independently selectable helmet sensors and the service recorder."""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    actions = [DeclareLaunchArgument('zed_params_file', default_value=PathJoinSubstitution([
        FindPackageShare('helmet_bringup'), 'config', 'zed_params.yaml'])),
        DeclareLaunchArgument('zed_enable_ipc', default_value='true')]
    for sensor in ('imu', 'lidar', 'zed', 'audio'):
        arg = 'launch_' + sensor
        actions.append(DeclareLaunchArgument(arg, default_value='true'))
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([
                FindPackageShare('helmet_bringup'), 'launch', sensor + '.launch.py',
            ])), condition=IfCondition(LaunchConfiguration(arg)),
            launch_arguments={'params_file': LaunchConfiguration('zed_params_file'),
                              'enable_ipc': LaunchConfiguration('zed_enable_ipc')}.items()
            if sensor == 'zed' else (),
        ))
    actions.extend([
        DeclareLaunchArgument('launch_recorder', default_value='true'),
        DeclareLaunchArgument('bag_directory', default_value=os.environ.get(
            'MUSOHU_BAG_DIR', os.path.expanduser('~/helmet_bags'))),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([
                FindPackageShare('musohu_bag_recorder'), 'launch', 'recorder.launch.py'])),
            condition=IfCondition(LaunchConfiguration('launch_recorder')),
            launch_arguments={'bag_directory': LaunchConfiguration('bag_directory')}.items()),
        DeclareLaunchArgument('launch_static_tf', default_value='true',
                              description='Publish finalized sensor extrinsics'),
        DeclareLaunchArgument('extrinsics_file', default_value=PathJoinSubstitution([
            FindPackageShare('helmet_bringup'), 'config', 'sensor_extrinsics.yaml'])),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([
                FindPackageShare('helmet_bringup'), 'launch', 'static_transforms.launch.py',
            ])), condition=IfCondition(LaunchConfiguration('launch_static_tf')),
            launch_arguments={'extrinsics_file': LaunchConfiguration('extrinsics_file')}.items(),
        ),
        DeclareLaunchArgument('launch_health_monitor', default_value='true'),
        Node(package='helmet_bringup', executable='sensor_health_monitor.py',
             name='musohu_sensor_health', output='screen',
             condition=IfCondition(LaunchConfiguration('launch_health_monitor')),
             parameters=[PathJoinSubstitution([
                 FindPackageShare('helmet_bringup'), 'config', 'sensor_health.yaml']),
                 {key + '.enabled': ParameterValue(LaunchConfiguration('launch_' + sensor),
                                                   value_type=bool)
                  for key, sensor in [('witmotion', 'imu'), ('zed', 'zed'), ('audio', 'audio')]}]),
    ])
    return LaunchDescription(actions)

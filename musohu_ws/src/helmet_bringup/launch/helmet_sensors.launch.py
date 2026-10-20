"""Bring up independently selectable helmet sensors."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    actions = [DeclareLaunchArgument('zed_params_file', default_value=PathJoinSubstitution([
        FindPackageShare('helmet_bringup'), 'config', 'zed_params.yaml']))]
    for sensor in ('imu', 'lidar', 'zed', 'audio'):
        arg = 'launch_' + sensor
        actions.append(DeclareLaunchArgument(arg, default_value='true'))
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([
                FindPackageShare('helmet_bringup'), 'launch', sensor + '.launch.py',
            ])), condition=IfCondition(LaunchConfiguration(arg)),
            launch_arguments={'params_file': LaunchConfiguration('zed_params_file')}.items()
            if sensor == 'zed' else (),
        ))
    actions.extend([
        DeclareLaunchArgument('launch_actions', default_value='false',
                              description='Publish legacy /action estimates from ZED odometry'),
        Node(package='helmet_bringup', executable='action_generator.py',
             name='action_generator', output='screen',
             condition=IfCondition(LaunchConfiguration('launch_actions'))),
    ])
    return LaunchDescription(actions)

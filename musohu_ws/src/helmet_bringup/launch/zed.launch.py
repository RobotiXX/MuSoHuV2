"""ZED 2i with GEN_3 visual-inertial tracking and MuSoHu overrides."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('camera_model', default_value='zed2i'),
        DeclareLaunchArgument('camera_name', default_value='zed2i'),
        DeclareLaunchArgument('serial_number', default_value='0'),
        DeclareLaunchArgument('publish_tf', default_value='true'),
        DeclareLaunchArgument('publish_map_tf', default_value='true'),
        DeclareLaunchArgument('params_file', default_value=PathJoinSubstitution([
            FindPackageShare('helmet_bringup'), 'config', 'zed_params.yaml',
        ])),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([
                FindPackageShare('zed_wrapper'), 'launch', 'zed_camera.launch.py',
            ])),
            launch_arguments={
                'camera_model': LaunchConfiguration('camera_model'),
                'camera_name': LaunchConfiguration('camera_name'),
                'serial_number': LaunchConfiguration('serial_number'),
                'publish_tf': LaunchConfiguration('publish_tf'),
                'publish_map_tf': LaunchConfiguration('publish_map_tf'),
                'ros_params_override_path': LaunchConfiguration('params_file'),
            }.items(),
        ),
    ])

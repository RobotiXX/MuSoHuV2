"""Launch the Elettra WT901 driver from the RobotiXX Humble fork."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('device', default_value='witImu',
                              description='Qt serial port name, e.g. witImu or ttyUSB0'),
        DeclareLaunchArgument('baud', default_value='115200'),
        DeclareLaunchArgument('frame_id', default_value='imu_link'),
        Node(
            package='witmotion_ros', executable='witmotion_ros_node',
            name='witmotion', output='screen',
            parameters=[PathJoinSubstitution([
                FindPackageShare('helmet_bringup'), 'config', 'imu_params.yaml',
            ]), {
                'port': LaunchConfiguration('device'),
                'baud_rate': ParameterValue(LaunchConfiguration('baud'), value_type=int),
                'imu_publisher.frame_id': LaunchConfiguration('frame_id'),
            }],
        ),
    ])

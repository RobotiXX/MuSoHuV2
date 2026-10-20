"""Capture ReSpeaker audio, speech, VAD and direction of arrival."""
from launch import LaunchDescription
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def generate_launch_description():
    return LaunchDescription([Node(
        package='respeaker_ros', executable='respeaker_node',
        name='respeaker_node', output='screen',
        parameters=[PathJoinSubstitution([
            FindPackageShare('helmet_bringup'), 'config', 'audio_params.yaml',
        ])],
    )])

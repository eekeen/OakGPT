"""Downstream simulator expiry; telemetry bridge remains independent of command bridge."""

import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, SetRemap


def generate_launch_description():
    plugin_directory = os.environ.get("OAK_EXPIRY_PLUGIN_DIR")
    if not plugin_directory:
        raise RuntimeError("Set OAK_EXPIRY_PLUGIN_DIR to the built Gazebo expiry plugin directory")
    config = Path(get_package_share_directory("oak_mission")) / "config"
    nav = Path(get_package_share_directory("nav2_bringup"))
    gz = Path(get_package_share_directory("ros_gz_sim"))
    return LaunchDescription(
        [
            DeclareLaunchArgument("world"),
            DeclareLaunchArgument("map"),
            DeclareLaunchArgument("params"),
            SetEnvironmentVariable("LIBGL_ALWAYS_SOFTWARE", "1"),
            SetEnvironmentVariable(
                "GZ_SIM_SYSTEM_PLUGIN_PATH",
                plugin_directory + os.pathsep + os.environ.get("GZ_SIM_SYSTEM_PLUGIN_PATH", ""),
            ),
            Node(package="oak_mission", executable="mission_watchdog", output="screen"),
            Node(
                package="oak_mission",
                executable="velocity_guard",
                parameters=[{"leased_output": True}],
                output="screen",
            ),
            Node(
                package="ros_gz_bridge",
                executable="parameter_bridge",
                name="oak_command_bridge",
                arguments=[
                    "/oak/leased_cmd_vel@geometry_msgs/msg/TwistStamped]gz.msgs.Twist",
                    "/oak/actuator_cmd@geometry_msgs/msg/Twist[gz.msgs.Twist",
                ],
                remappings=[("/oak/actuator_cmd", "/cmd_vel")],
                output="screen",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(str(gz / "launch/gz_sim.launch.py")),
                launch_arguments={
                    "gz_args": ["-r -s --headless-rendering ", LaunchConfiguration("world")]
                }.items(),
            ),
            Node(
                package="ros_gz_bridge",
                executable="parameter_bridge",
                arguments=[
                    "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
                    "/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan",
                    "/odom@nav_msgs/msg/Odometry[gz.msgs.Odometry",
                    "/tf@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V",
                    "/oak/expiry_events@std_msgs/msg/String[gz.msgs.StringMsg",
                    "/model/oak_robot/pose@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V",
                ],
                remappings=[("/model/oak_robot/pose", "/oak/ground_truth")],
                output="screen",
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                parameters=[
                    {"use_sim_time": True, "robot_description": (config / "robot.urdf").read_text()}
                ],
            ),
            GroupAction(
                [
                    SetRemap(src="docking_server:cmd_vel", dst="/cmd_vel_nav"),
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(str(nav / "launch/bringup_launch.py")),
                        launch_arguments={
                            "map": LaunchConfiguration("map"),
                            "params_file": LaunchConfiguration("params"),
                            "use_sim_time": "True",
                            "autostart": "True",
                            "use_composition": "False",
                        }.items(),
                    ),
                ]
            ),
        ]
    )

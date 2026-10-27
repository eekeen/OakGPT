from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    share = Path(get_package_share_directory("oak_mission"))
    config = share / "config"
    nav = Path(get_package_share_directory("nav2_bringup"))
    gz = Path(get_package_share_directory("ros_gz_sim"))
    return LaunchDescription(
        [
            Node(package="oak_mission", executable="mission_watchdog", output="screen"),
            SetEnvironmentVariable("LIBGL_ALWAYS_SOFTWARE", "1"),
            SetEnvironmentVariable("GZ_SIM_RESOURCE_PATH", str(config)),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(str(gz / "launch/gz_sim.launch.py")),
                launch_arguments={
                    "gz_args": f"-r -s --headless-rendering {config / 'room.sdf'}"
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
                    "/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist",
                ],
                output="screen",
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                parameters=[
                    {"use_sim_time": True, "robot_description": (config / "robot.urdf").read_text()}
                ],
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(str(nav / "launch/bringup_launch.py")),
                launch_arguments={
                    "map": str(config / "room.yaml"),
                    "params_file": str(config / "nav2.yaml"),
                    "use_sim_time": "True",
                    "autostart": "True",
                    "use_composition": "False",
                }.items(),
            ),
        ]
    )

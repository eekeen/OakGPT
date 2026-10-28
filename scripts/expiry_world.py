"""Transform only fresh trial copies; never edit historical worlds."""

import xml.etree.ElementTree as ET
from pathlib import Path


def enable_expiry(world: Path) -> None:
    path = world / "world.sdf"
    tree = ET.parse(path)
    robot = tree.getroot().find("world/model[@name='oak_robot']")
    if robot is None:
        raise ValueError("Expected oak_robot model")
    drives = robot.findall("plugin[@name='gz::sim::systems::DiffDrive']/topic")
    if len(drives) != 1 or drives[0].text != "/cmd_vel":
        raise ValueError("Unexpected downstream command route")
    drives[0].text = "/oak/actuator_cmd"
    ET.SubElement(
        robot, "plugin", filename="liboak_command_expiry.so", name="oak_expiry::GazeboExpiry"
    )
    tree.write(path, encoding="unicode")

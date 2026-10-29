"""Seeded local worlds/maps with independent simulator pose publication."""

import argparse
import json
import math
import random
import xml.etree.ElementTree as ET
from pathlib import Path

LAYOUTS = {
    "empty": [],
    "center_block": [{"x": 0.4, "y": 0.4, "sx": 0.26, "sy": 0.26}],
    "offset_wall": [{"x": 0.4, "y": -0.4, "sx": 0.12, "sy": 1.0}],
}


def create_world(output, layout, seed):
    output.mkdir(parents=True, exist_ok=False)
    root = Path("robotics/ros2_ws/src/oak_mission/config")
    tree = ET.parse(root / "room.sdf")
    world = tree.getroot().find("world")
    robot = world.find("model[@name='oak_robot']")
    rng = random.Random(seed)
    x, y, yaw = rng.uniform(-0.25, -0.05), rng.uniform(-0.2, 0.2), rng.uniform(-0.3, 0.3)
    robot.find("pose").text = f"{x} {y} 0.12 0 0 {yaw}"
    plugin = ET.SubElement(
        robot,
        "plugin",
        filename="gz-sim-pose-publisher-system",
        name="gz::sim::systems::PosePublisher",
    )
    for name, value in {
        "publish_link_pose": "false",
        "publish_model_pose": "true",
        "use_pose_vector_msg": "true",
        "update_frequency": "30",
    }.items():
        ET.SubElement(plugin, name).text = value
    obstacles = LAYOUTS[layout]
    for index, obstacle in enumerate(obstacles):
        model = ET.SubElement(world, "model", name=f"obstacle_{index}")
        ET.SubElement(model, "static").text = "true"
        ET.SubElement(model, "pose").text = f"{obstacle['x']} {obstacle['y']} .35 0 0 0"
        link = ET.SubElement(model, "link", name="body")
        for kind in ["collision", "visual"]:
            shape = ET.SubElement(link, kind, name="box")
            box = ET.SubElement(ET.SubElement(shape, "geometry"), "box")
            ET.SubElement(box, "size").text = f"{obstacle['sx']} {obstacle['sy']} .7"
    tree.write(output / "world.sdf", encoding="unicode", xml_declaration=True)
    pixels = bytearray()
    for row in range(160):
        for column in range(160):
            px, py = -4 + (column + 0.5) * 0.05, 4 - (row + 0.5) * 0.05
            occupied = (
                abs(px) >= 3.9
                or abs(py) >= 3.9
                or any(
                    abs(px - b["x"]) <= b["sx"] / 2 and abs(py - b["y"]) <= b["sy"] / 2
                    for b in obstacles
                )
            )
            pixels.append(0 if occupied else 254)
    (output / "map.pgm").write_bytes(b"P5\n160 160\n255\n" + pixels)
    (output / "map.yaml").write_text(
        "image: map.pgm\nresolution: 0.05\norigin: [-4, -4, 0]\nnegate: 0\n"
        "occupied_thresh: 0.65\nfree_thresh: 0.196\n"
    )
    text = (root / "nav2.yaml").read_text()
    text = text.replace(
        "initial_pose:\n      x: 0.0\n      y: 0.0\n      z: 0.0\n      yaw: 0.0",
        f"initial_pose:\n      x: {x + 0.03}\n      y: {y - 0.02}\n"
        f"      z: 0.0\n      yaw: {yaw + 0.02}",
    )
    if text == (root / "nav2.yaml").read_text():
        raise ValueError(
            "Initial-pose parameter format changed; refusing an incorrect map alignment"
        )
    if "cmd_vel_out_topic: cmd_vel" not in text:
        raise ValueError("Collision-monitor output parameter changed")
    text = text.replace("cmd_vel_out_topic: cmd_vel", "cmd_vel_out_topic: oak/nav_cmd_vel")
    (output / "nav2.yaml").write_text(text)
    spec = {
        "layout": layout,
        "seed": seed,
        "start": {"x": x, "y": y, "yaw": yaw},
        "amcl_initial_error": {"x": 0.03, "y": -0.02, "yaw": 0.02},
        "obstacles": obstacles,
        "truth": "Gazebo model world pose, distinct from wheel odometry and AMCL",
        "map_world_alignment": "identity by construction",
        "physics_step_s": 0.01,
        "truth_frequency_hz": 30,
    }
    (output / "world.json").write_text(json.dumps(spec, indent=2))
    assert all(
        math.hypot(max(abs(x - b["x"]) - b["sx"] / 2, 0), max(abs(y - b["y"]) - b["sy"] / 2, 0))
        > 0.3
        for b in obstacles
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    for layout in LAYOUTS:
        for seed in [41, 42, 43]:
            create_world(args.output / f"{layout}-{seed}", layout, seed)


if __name__ == "__main__":
    main()

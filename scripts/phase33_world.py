"""Contact sensors on fresh world copies only, independent of clearance estimates."""

import xml.etree.ElementTree as ET


def instrument_world(directory):
    path = directory / "world.sdf"
    tree = ET.parse(path)
    world = tree.getroot().find("world")
    ET.SubElement(
        world, "plugin", filename="gz-sim-contact-system", name="gz::sim::systems::Contact"
    )
    robot = world.find("model[@name='oak_robot']")
    for link in robot.findall("link"):
        for collision in link.findall("collision"):
            name = link.get("name") + "_" + collision.get("name")
            sensor = ET.SubElement(link, "sensor", name="contact_" + name, type="contact")
            ET.SubElement(sensor, "always_on").text = "true"
            ET.SubElement(sensor, "update_rate").text = "100"
            ET.SubElement(sensor, "topic").text = "/oak/contacts/" + name
            ET.SubElement(ET.SubElement(sensor, "contact"), "collision").text = collision.get(
                "name"
            )
    tree.write(path, encoding="unicode")

from glob import glob

from setuptools import setup

setup(
    name="oak_mission",
    version="0.1.0",
    packages=["oak_mission"],
    tests_require=["pytest"],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/oak_mission"]),
        ("share/oak_mission", ["package.xml"]),
        ("share/oak_mission/launch", glob("launch/*.py")),
        ("share/oak_mission/config", glob("config/*")),
    ],
    entry_points={
        "console_scripts": [
            "mission_executor = oak_mission.executor:main",
            "mission_watchdog = oak_mission.watchdog:main",
            "velocity_guard = oak_mission.velocity_guard:main",
            "mission_observer = oak_mission.observer:main",
        ]
    },
)

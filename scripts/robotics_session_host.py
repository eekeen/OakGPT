"""Windows host ownership for one ROS/Gazebo session; no process-name-wide cleanup."""

import contextlib
import subprocess
import time
from pathlib import Path

from reproduce_phase31 import wsl_path


@contextlib.contextmanager
def session(
    root,
    world,
    install,
    launch="reliability.launch.py",
    navigation_trace=True,
    expiry_plugin_dir="/home/eekeen/projects/oak-expiry-build",
    fastdds_profile=None,
):
    project = Path.cwd().resolve()
    command = [
        "wsl.exe",
        "-d",
        "Ubuntu-24.04",
        "--",
        "env",
        f"OAK_ROS_INSTALL={install}",
        f"OAK_EXPIRY_PLUGIN_DIR={expiry_plugin_dir}",
        "OAK_FASTDDS_PROFILE=" + (wsl_path(fastdds_profile) if fastdds_profile else ""),
        "GZ_PARTITION=oak32-" + root.parent.name + "-" + root.name,
        "bash",
        wsl_path(project / "scripts/robotics_session.sh"),
        "--directory",
        wsl_path(root),
        "--project",
        wsl_path(project),
        "--world-directory",
        wsl_path(world),
        "--launch-name",
        launch,
        "--bag",
        f"/home/eekeen/projects/oak-bags/phase32-{root.parent.name}-{root.name}",
    ]
    if navigation_trace:
        command.append("--navigation-trace")
    with (root / "supervisor.log").open("x") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 120
            while not (root / "READY.json").exists():
                if process.poll() is not None:
                    raise RuntimeError("Session startup failed")
                if time.monotonic() > deadline:
                    raise TimeoutError("Readiness deadline")
                time.sleep(0.2)
            yield
        finally:
            (root / "STOP_SESSION").touch()
            process.wait(timeout=30)

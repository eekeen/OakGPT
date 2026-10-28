"""Check archive bytes, cohort completeness and the approved linguistic fixture."""

import argparse
import json
from pathlib import Path

from oakgpt.provenance import sha256
from oakgpt.robotics.language import reviewed_rows


def verify_manifest(root):
    manifest = json.loads((root / "manifest.json").read_text())
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(manifest) | {"manifest.json"}:
        raise ValueError("Archive has missing or unlisted files")
    for name, expected in manifest.items():
        path = root / name
        if path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
            raise ValueError(f"Evidence changed: {name}")
    return len(manifest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check-current-runtime",
        action="store_true",
        help="Also require current ROS source to match measured installations",
    )
    args = parser.parse_args()
    root = Path("reports/phase31/raw")
    raw_files = verify_manifest(root)
    qa_files = verify_manifest(Path("reports/phase31/qa-final"))
    studies = list((root / "reproduction-v1").glob("session-*/study/study.json"))
    assert len(studies) == 3
    for path in studies:
        assert len(json.loads(path.read_text())["records"]) == 180
    ground = json.loads((root / "ground-formal-v1/ground_truth.json").read_text())
    assert len(ground["trials"]) == 9
    for path in (root / "ground-formal-v1").glob("*/result.json"):
        record = json.loads(path.read_text())
        assert sha256(path.with_name("trajectory.jsonl")) == record["trajectory_sha256"]
    matrix = root / "fault-comparison-v4/fault-hardened-v4"
    assertions = json.loads((matrix / "assertions.json").read_text())
    assert assertions == {"failures": [], "require_safe": True, "complete": True}
    assert len(json.loads((matrix / "matrix.json").read_text())["records"]) == 21
    assert len(json.loads((root / "language-v3/language.json").read_text())["records"]) == 180
    assert len(reviewed_rows(Path("data/robotics/linguistic_v2"))) == 60
    critical = ["executor.py", "watchdog.py", "velocity_guard.py", "guard_rules.py", "observer.py"]
    runtime = Path("robotics/ros2_ws/src/oak_mission/oak_mission")
    ready_files = [
        *sorted((root / "ground-formal-v1").glob("*/READY.json")),
        *sorted((root / "language-v3").glob("*/READY.json")),
    ]
    assert len(ready_files) == 12
    if args.check_current_runtime:
        for path in ready_files:
            installed = json.loads(path.read_text())["installed_ros_source_sha256"]
            for name in critical:
                assert sha256(runtime / name) == installed[name], (path, name)
        print("Current ROS source matches all 12 measured instrumented installations")
    print(f"Verified {raw_files} raw and {qa_files} final-QA hashes and cohort counts")


if __name__ == "__main__":
    main()

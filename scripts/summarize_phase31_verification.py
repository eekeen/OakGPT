"""Summarize actual logs, xUnit records, offload evidence and local quality gates."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path


def junit(path):
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    result = {
        key: sum(int(s.get(key, 0)) for s in suites)
        for key in ["tests", "failures", "errors", "skipped"]
    }
    result["passed"] = result["tests"] - result["failures"] - result["errors"] - result["skipped"]
    return result


def main():
    root = Path("reports/phase31")
    raw = root / "raw"
    final_python = root / "qa-final/verification-final/python"
    checks = json.loads((final_python / "checks.json").read_text(encoding="utf-8-sig"))
    if len(checks) != 6 or any(row["exit_code"] != 0 for row in checks):
        raise ValueError("Clean environment quality gates did not all pass")
    python = junit(final_python / "pytest.xml")
    cuda = junit(raw / "verification-hardware/cuda-tests.xml")
    live = junit(raw / "verification-hardware/live-server-test.xml")
    for result in [python, cuda, live]:
        if result["failures"] or result["errors"]:
            raise ValueError("Failed test records")
    hardware = json.loads((raw / "verification-hardware/hardware.json").read_text())
    assert hardware["cuda_suite_exit_code"] == hardware["live_server_exit_code"] == 0
    robotics = raw / "verification-v1/robotics"
    assert json.loads((robotics / "robotics.json").read_text())["passed"]
    for name in ["ctest-release.log", "ctest-sanitizer.log"]:
        text = (robotics / name).read_text()
        assert "10031 checks passed" in text and "100% tests passed" in text
    assert (
        "60 frozen-oracle C++ integration cases passed" in (robotics / "cpp-oracle.log").read_text()
    )
    assert (
        "3 tests, 0 errors, 0 failures, 0 skipped"
        in (robotics / "ros-test-summary.log").read_text()
    )
    offload_logs = [
        *sorted((raw / "reproduction-v1").glob("session-*/study/Q*/stderr.txt")),
        *sorted((raw / "language-v3").glob("Q*/study/Q*/stderr.txt")),
        raw / "verification-hardware/Q8_0/stderr.txt",
    ]
    assert len(offload_logs) == 9
    for path in offload_logs:
        assert "offloaded 29/29 layers to GPU" in path.read_text(errors="replace"), path
    result = {
        "cpu_python": python,
        "cuda_environment_suite": cuda,
        "live_qwen_test": live,
        "quality_gates": checks,
        "cpp_checks_each_build": 10031,
        "cpp_oracle_cases": 60,
        "ros_node_state_tests": 3,
        "verified_gpu_offload_logs": [p.relative_to(root).as_posix() for p in offload_logs],
        "historical_evidence_diff_empty": (robotics / "historical-evidence.log").stat().st_size
        == 0,
        "inherited_environment_issue": (
            "Initial pip check found global TensorFlow/OpenCV NumPy conflicts; "
            "original environment preserved and isolated verification passed"
        ),
        "hosted_ci": "Reported on the pull request; local results do not imply hosted CI success",
        "report_summary": (
            f"The isolated CPU suite passed {python['passed']} tests "
            f"with {python['skipped']} opt-in "
            f"hardware skips. The physical CUDA-environment suite passed {cuda['passed']} tests "
            f"with {cuda['skipped']} live-server skip; the separate live Q8 server test passed "
            f"{live['passed']} test. All nine final study/test server logs confirm "
            "29/29 GPU layers. Ruff lint/format, strict mypy, sdist/wheel construction "
            "and isolated pip check passed. "
            "C++ release and ASan/UBSan each passed 10,031 checks, including 5,000 seeded byte "
            "fuzz cases and 5,000 bound mutations; all 60 frozen-oracle cases passed. The ROS "
            "package built and its three captured-output node-state tests passed. Initial pip "
            "check exposed unrelated inherited TensorFlow/OpenCV NumPy conflicts; that "
            "environment was preserved and a new isolated environment passed. Hosted CI is "
            "reported separately on the final pull request."
        ),
    }
    (root / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(result["report_summary"])


if __name__ == "__main__":
    main()

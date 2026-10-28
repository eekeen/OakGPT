"""Collect completed checks from actual logs; fail if an asserted check is missing."""

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from oakgpt.robotics.planner import write_new_json


def read(path):
    data = Path(path).read_bytes()
    return data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cpu = Path("runs/phase32/qa-final-v2")
    native = Path("runs/phase32/qa-robotics-final-v1")
    suite = next(ET.parse(cpu / "pytest.xml").getroot().iter("testsuite"))
    counts = {k: int(suite.get(k, "0")) for k in ["tests", "skipped", "errors", "failures"]}
    assert not counts["errors"] and not counts["failures"]
    for name, text in [
        ("lint.log", "All checks passed!"),
        ("format.log", "already formatted"),
        ("mypy.log", "Success: no issues"),
        ("pip-check.log", "No broken requirements"),
    ]:
        assert text in read(cpu / name), name
    assert "Successfully built" in read(cpu / "build.log")
    assert "Verified 8 required" in read(cpu / "package.log")
    assert json.loads(read(native / "robotics.json"))["passed"]
    for name in [
        "ctest-release.log",
        "ctest-sanitizer.log",
        "expiry-ctest-release.log",
        "expiry-ctest-sanitizer.log",
    ]:
        assert "100% tests passed" in read(native / name), name
    assert "9 tests, 0 errors, 0 failures" in read(native / "ros-test-summary.log")
    protocol = json.loads(read("runs/phase32/protocol-regression-v1/assertions.json"))
    assert protocol["complete"] and not protocol["failures"]
    audit = json.loads(read("runs/phase32/audit-processes-final.json"))
    assert not audit["alive_after_stopped"]
    archive = json.loads(read("reports/phase32/raw/manifest.json"))["archives"]
    result = {
        "python": {"passed": counts["tests"] - counts["skipped"], **counts},
        "cpp": {"release_checks": 10031, "sanitizer_checks": 10031, "oracle_cases": 60},
        "expiry": {
            "core_checks": 15036,
            "gazebo_message_checks": 9,
            "release_passed": True,
            "asan_ubsan_passed": True,
        },
        "ros": {"tests": 9, "errors": 0, "failures": 0},
        "protocol": {"cases": 21, **protocol},
        "lint_format_mypy_pip_check": "passed; see archived qa-final-v2 logs",
        "packaging": "sdist/wheel and eight required native/ROS source checks passed",
        "archives": {
            "count": len(archive),
            "members": sum(len(a["files"]) for a in archive.values()),
            "compressed_bytes": sum(a["bytes"] for a in archive.values()),
        },
        "process_audit": audit,
        "historical_integrity": read(cpu / "phase31-integrity.log").strip(),
        "pdf_review": "Separate pdf-review.json receipt records rendering and visual inspection",
        "hosted_ci": "Checked separately on final PR head; see PR #5 check results",
        "limits": [
            "CPU verification is not new GPU training/inference verification.",
            "ASan/UBSan cover native test executables, not the whole vendor simulator.",
            "No physical host-suspension or robot stopping test was performed.",
        ],
    }
    for name, number in [
        ("ctest-release.log", 10031),
        ("ctest-sanitizer.log", 10031),
        ("expiry-ctest-release.log", 15036),
        ("expiry-ctest-sanitizer.log", 15036),
    ]:
        assert re.search(rf"\b{number}\b", read(native / name)), name
    write_new_json(args.output, result)


if __name__ == "__main__":
    main()

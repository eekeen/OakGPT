"""A transient DrvFS read failure cannot become stale-motion evidence."""

import errno
import importlib.util
import json
from pathlib import Path


def test_transient_read_error_is_recorded_and_requires_fresh_motion(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "fault_precondition", "scripts/fault_precondition.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    trace = tmp_path / "trajectory.jsonl"
    trace.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {"kind": "truth", "monotonic_ns": 0, "sim_ns": 0, "x": 0, "y": 0},
                {
                    "kind": "truth",
                    "monotonic_ns": 100000000,
                    "sim_ns": 100000000,
                    "x": 0.01,
                    "y": 0,
                },
                {"kind": "command", "monotonic_ns": 95000000, "vx": 0.1, "wz": 0},
            ]
        )
    )
    original = Path.open
    calls = []

    def flaky_open(path, *args, **kwargs):
        if path == trace and not calls:
            calls.append("transient")
            raise OSError(errno.ENODATA, "No data available")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", flaky_open)
    monkeypatch.setattr(module.time, "monotonic_ns", lambda: 110000000)
    result = module.wait_motion(trace, timeout=0.2)
    assert result["eligible"] and result["read_errors"] == {str(errno.ENODATA): 1}
    assert result["truth_age_s"] == 0.01

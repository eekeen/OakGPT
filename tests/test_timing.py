"""Timestamp-domain semantics and tracing must not alter fault handling."""

import importlib.util
import json

from oakgpt.robotics.timing import analyze_timing


def module():
    spec = importlib.util.spec_from_file_location(
        "timing", "robotics/ros2_ws/src/oak_mission/oak_mission/timing.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_explicit_clock_domains_and_nonfinite_fault_values(tmp_path, monkeypatch):
    timing = module()
    monkeypatch.setenv("OAK_TIMING_DIR", str(tmp_path))
    monkeypatch.setattr(timing.time, "CLOCK_BOOTTIME", 7, raising=False)
    monkeypatch.setattr(timing.time, "clock_gettime_ns", lambda clock: 12345, raising=False)
    monkeypatch.setattr(timing.time, "monotonic_ns", lambda: 12000)
    monkeypatch.setattr(timing.time, "thread_time_ns", lambda: 345)
    recorder = timing.Timing()
    recorder.record("guard_receipt", vx=float("nan"))
    row = json.loads(next(tmp_path.iterdir()).read_text())
    assert row["boot_ns"] == 12345 and row["mono_ns"] == 12000
    assert row["thread_cpu_ns"] == 345 and row["vx"] == "nan"
    timing.os.close(recorder.fd)


def test_recording_failure_does_not_interrupt_control(tmp_path, monkeypatch):
    timing = module()
    monkeypatch.setattr(timing.time, "CLOCK_BOOTTIME", 7, raising=False)
    monkeypatch.setattr(timing.time, "clock_gettime_ns", lambda clock: 12345, raising=False)
    monkeypatch.setenv("OAK_TIMING_DIR", str(tmp_path))
    recorder = timing.Timing()
    timing.os.close(recorder.fd)
    recorder.record("guard_tick")
    assert recorder.errors == 1


def test_disabled_tracing_does_not_touch_clock(monkeypatch):
    timing = module()
    monkeypatch.delenv("OAK_TIMING_DIR", raising=False)
    recorder = timing.Timing()
    monkeypatch.setattr(timing.time, "monotonic_ns", lambda: 1 / 0)
    recorder.record("disabled")
    assert recorder.fd is None and recorder.errors == 0


def test_transport_analysis_uses_only_compatible_clocks():
    rows = [
        {
            "stage": stage,
            "boot_ns": stamp,
            "thread_cpu_ns": 10,
            "pid": 1,
            "sequence": 7,
            "dds_source_realtime_ns": 999999999999999999,
        }
        for stage, stamp in [
            ("guard_publish_begin", 100),
            ("dds_take", 200),
            ("gz_publish_begin", 240),
            ("native_decoded", 300),
        ]
    ]
    result = analyze_timing(rows)
    edges = result["matched_command_edges"]
    assert edges["guard_publish_begin->native_decoded"]["median_ns"] == 200
    assert edges["dds_take->gz_publish_begin"]["median_ns"] == 40

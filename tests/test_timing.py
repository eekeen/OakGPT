"""Timestamp-domain semantics and tracing must not alter fault handling."""

import importlib.util
import json

from oakgpt.robotics.timing import analyze_timing, expiration_bracket_valid


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


def test_expiration_boundary_rejects_clock_jumps_or_coarse_observation():
    assert expiration_bracket_valid(
        10_000_000_000, 100_000, 10_001_000_000, 1_100_000, 10_000_500_000
    )
    assert not expiration_bracket_valid(
        10_000_000_000, 100_000, 11_000_000_000, 1_100_000, 10_000_500_000
    )
    assert not expiration_bracket_valid(
        10_000_000_000, 100_000, 10_100_000_000, 100_100_000, 10_000_500_000
    )
    assert not expiration_bracket_valid(
        10_000_000_000, 100_000, 10_001_000_000, 1_100_000, 9_999_999_999
    )


def test_unavailable_trace_directory_does_not_prevent_control(tmp_path, monkeypatch):
    timing = module()
    monkeypatch.setenv("OAK_TIMING_DIR", str(tmp_path / "missing"))
    recorder = timing.Timing()
    assert recorder.fd is None and recorder.errors == 1
    recorder.record("guard_tick")


def test_tail_statistics_are_explicit():
    from oakgpt.robotics.timing import distribution

    result = distribution(list(range(100)))
    assert result["p95_ns"] == 95 and result["p99_ns"] == 99
    assert distribution([])["p95_ns"] is None


def test_native_stream_gaps_cross_worker_threads_and_keep_missingness():
    rows = [
        {
            "stage": "guard_publish_begin",
            "boot_ns": 1,
            "thread_cpu_ns": 0,
            "pid": 1,
            "sequence": 7,
            "vx": 0.2,
        },
        {
            "stage": "native_decoded",
            "boot_ns": 2,
            "thread_cpu_ns": 0,
            "pid": 2,
            "tid": 20,
            "sequence": 7,
        },
        {
            "stage": "native_decoded",
            "boot_ns": 300000002,
            "thread_cpu_ns": 0,
            "pid": 2,
            "tid": 21,
            "sequence": 8,
        },
    ]
    result = analyze_timing(rows)["command_stream"]
    assert result["native_gaps_over_200ms"] == 1
    assert result["gaps_over_200ms_following_nonzero"] == 1
    assert result["nonzero_guard_begin_to_native"]["n"] == 1
    assert result["native_state_reasons"] == {}

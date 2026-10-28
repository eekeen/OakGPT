import importlib.util
import json


def test_unattempted_missions_remain_in_completion_denominator(tmp_path):
    spec = importlib.util.spec_from_file_location("phase32_analysis", "scripts/analyze_phase32.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = tmp_path / "empty-1"
    (case / "world").mkdir(parents=True)
    (case / "world/world.json").write_text(
        json.dumps({"layout": "empty", "seed": 1, "obstacles": []})
    )
    mission = {
        "mission": {"instruction": "Go to station", "steps": [{"destination": "station"}]},
        "result": {
            "status": "completed",
            "reason": "ok",
            "execution_seconds": 1,
            "events": [
                {"event": "accepted", "sim_time_ns": 0},
                {"event": "arrived", "sim_time_ns": 1000000000},
            ],
        },
    }
    (case / "result.json").write_text(
        json.dumps(
            {
                "missions": [mission],
                "environment_failure": "Disconnected before next dispatch",
                "localization": {"matches": []},
            }
        )
    )
    rows = [{"kind": "truth", "sim_ns": t, "x": 0.8, "y": 0} for t in [0, 1000000000]]
    rows.append({"kind": "command", "vx": 0, "wz": 0})
    (case / "trajectory.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    result = module.navigation_cohort(tmp_path)
    assert result["planned"] == 3 and result["attempted"] == result["completed"] == 1
    assert [m["status"] for m in result["missions"]] == [
        "completed",
        "not_attempted",
        "not_attempted",
    ]
    assert result["all_completed_worlds"] == 0
    assert result["completed_arrival_within_0_35m"] == 1
    assert not result["acceptance"]["33_of_36_completed"]


def test_partial_fault_result_is_retained_without_claiming_a_motion_measurement(tmp_path):
    spec = importlib.util.spec_from_file_location("phase32_analysis", "scripts/analyze_phase32.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = tmp_path / "watchdog_crash"
    case.mkdir()
    (case / "result.json").write_text(
        json.dumps(
            {
                "injection": {"before_monotonic_ns": 10},
                "environment_failure": "Recorder unavailable after injection",
            }
        )
    )
    result = module.fault_cohort(tmp_path)
    assert result["planned"] == 1 and result["eligible"] == 0
    assert result["eligible_stopping_target_passes"] == 0
    assert result["trials"][0]["environment_failure"] == "Recorder unavailable after injection"

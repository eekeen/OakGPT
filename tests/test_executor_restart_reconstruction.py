"""Archived restart failure remains a failure; missing recovery stays unavailable."""

import importlib

import pytest


def test_original_restart_timeline_is_not_reinterpreted_as_success(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    module = importlib.import_module("reconstruct_executor_restart")
    result = module.reconstruct("reports/phase33/final-faults-v1/raw/executor_restart.tar.gz")
    events = {r["event"]: r for r in result["timeline"]}
    assert events["guard zero publication begins"]["relative_monotonic_s"] == pytest.approx(
        0.41857551
    )
    assert events["native receives zero target"]["relative_monotonic_s"] == pytest.approx(
        0.41934384
    )
    assert result["native_stopping"]["stop_latency_sim_s"] == 0.6
    assert result["observer_stopping"]["stop_latency_sim_s"] == 0.6
    assert result["restart_probe_result"] is None
    assert "verified restart authorization" in result["unavailable"]
    assert events["replacement process spawned"]["limitation"]
    assert events["native receives zero target"]["limitation"]

import importlib.util
import json

import pytest


def load_clock():
    spec = importlib.util.spec_from_file_location("trial_clock", "scripts/trial_clock.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preparation_retry_records_rejection_and_uses_only_successful_reply(monkeypatch, tmp_path):
    module = load_clock()
    replies = iter([RuntimeError("RTT exceeded bound"), 123456])

    def reply(command):
        value = next(replies)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(module, "receiver_clock", reply)
    output = tmp_path / "clock.jsonl"
    assert module.trial_clock(["receiver"], output) == 123456
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert [r["accepted"] for r in rows] == [False, True]
    assert rows[0]["reason"] == "RTT exceeded bound"


def test_preparation_fails_after_three_rejected_handshakes(monkeypatch, tmp_path):
    module = load_clock()

    def reject(command):
        raise RuntimeError("Invalid clock reply")

    monkeypatch.setattr(module, "receiver_clock", reject)
    output = tmp_path / "clock.jsonl"
    with pytest.raises(RuntimeError, match="All three"):
        module.trial_clock(["receiver"], output)
    assert len(output.read_text().splitlines()) == 3

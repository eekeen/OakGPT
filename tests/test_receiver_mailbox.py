"""Clock preparation preserves the actual C++ JSON protocol and nonce binding."""

import importlib.util
import json
from types import SimpleNamespace

import pytest


def module():
    spec = importlib.util.spec_from_file_location(
        "receiver_clock_mailbox", "scripts/receiver_clock_mailbox.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_server_uses_cpp_json_clock_and_serves_nonce_once(tmp_path, monkeypatch):
    clock = module()
    nonce = "a" * 32
    (tmp_path / "clock_requests").mkdir()
    (tmp_path / "clock_requests" / (nonce + ".json")).write_text(json.dumps({"nonce": nonce}))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout='{"now_ms":123456}')

    monkeypatch.setattr(clock.subprocess, "run", run)
    clock.serve_clock(tmp_path, "/validator")
    clock.serve_clock(tmp_path, "/validator")
    reply = json.loads((tmp_path / "clock_replies" / (nonce + ".json")).read_text())
    assert reply["nonce"] == nonce and reply["receiver_now_ms"] == 123456
    assert calls == [["/validator", "--clock"]]


def test_invalid_challenge_never_runs_a_command(tmp_path, monkeypatch):
    clock = module()
    (tmp_path / "clock_requests").mkdir()
    (tmp_path / "clock_requests" / "bad.json").write_text('{"nonce":"../../unsafe"}')
    monkeypatch.setattr(clock.subprocess, "run", lambda *a, **k: 1 / 0)
    clock.serve_clock(tmp_path, "/validator")
    assert not (tmp_path / "clock_replies").exists()


def test_client_rejects_stale_nonce(tmp_path, monkeypatch):
    import pytest

    clock = module()
    nonce = "b" * 32
    monkeypatch.setattr(clock.uuid, "uuid4", lambda: SimpleNamespace(hex=nonce))
    (tmp_path / "clock_replies").mkdir()
    (tmp_path / "clock_replies" / (nonce + ".json")).write_text(
        '{"nonce":"old","receiver_now_ms":123}'
    )
    with pytest.raises(RuntimeError, match="replay"):
        clock.request_clock(tmp_path)


def test_client_keeps_one_second_freshness_bound(tmp_path, monkeypatch):
    import pytest

    clock = module()
    values = iter([0, 1.01])
    monkeypatch.setattr(clock.time, "monotonic", lambda: next(values))
    with pytest.raises(RuntimeError, match="one second"):
        clock.request_clock(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        {"nonce": "c" * 32},
        {"receiver_now_ms": True},
        {"receiver_now_ms": 0},
        {"receiver_now_ms": 9007199254740991},
        {"responded_monotonic_ns": 1},
        {"received_monotonic_ns": "2"},
        {"responded_monotonic_ns": 2000000000},
        {"clock_source": "untrusted"},
        {"extra": 1},
    ],
)
def test_corrupted_reply_cannot_produce_a_clock(tmp_path, monkeypatch, mutation):
    clock = module()
    nonce = "b" * 32
    monkeypatch.setattr(clock.uuid, "uuid4", lambda: SimpleNamespace(hex=nonce))

    def respond(_):
        reply = tmp_path / "clock_replies" / (nonce + ".json")
        reply.parent.mkdir(exist_ok=True)
        payload = {
            "nonce": nonce,
            "receiver_now_ms": 123,
            "received_monotonic_ns": 2,
            "responded_monotonic_ns": 3,
            "clock_source": "/validator --clock",
        }
        payload.update(mutation)
        reply.write_text(json.dumps(payload))

    monkeypatch.setattr(clock.time, "sleep", respond)
    with pytest.raises(RuntimeError, match="Corrupted"):
        clock.request_clock(tmp_path)


def test_roundtrip_and_replay_rejection(tmp_path, monkeypatch):
    clock = module()
    nonce = "d" * 32
    monkeypatch.setattr(clock.uuid, "uuid4", lambda: SimpleNamespace(hex=nonce))
    monkeypatch.setattr(
        clock.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout='{"now_ms":123}')
    )
    monkeypatch.setattr(clock.time, "sleep", lambda _: clock.serve_clock(tmp_path, "/validator"))
    assert clock.request_clock(tmp_path) == 123
    with pytest.raises(RuntimeError, match="replay"):
        clock.request_clock(tmp_path)


@pytest.mark.parametrize(
    "raw", ["{}", "[]", '{"now_ms":1,"now_ms":2}', '{"now_ms":true}', '{"now_ms":NaN}']
)
def test_corrupt_cpp_response_never_creates_reply(tmp_path, monkeypatch, raw):
    clock = module()
    nonce = "a" * 32
    requests = tmp_path / "clock_requests"
    requests.mkdir()
    (requests / (nonce + ".json")).write_text(json.dumps({"nonce": nonce}))
    monkeypatch.setattr(clock.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=raw))
    clock.serve_clock(tmp_path, "/validator")
    assert not list((tmp_path / "clock_replies").glob("*.json"))


def test_reply_arriving_after_one_second_is_rejected(tmp_path, monkeypatch):
    clock = module()
    nonce = "e" * 32
    monkeypatch.setattr(clock.uuid, "uuid4", lambda: SimpleNamespace(hex=nonce))
    values = iter([0, 0, 0.9, 1.001, 1.001])
    monkeypatch.setattr(clock.time, "monotonic", lambda: next(values))
    monkeypatch.setattr(
        clock.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout='{"now_ms":123}')
    )
    monkeypatch.setattr(clock.time, "sleep", lambda _: clock.serve_clock(tmp_path, "/validator"))
    with pytest.raises(RuntimeError, match="one second"):
        clock.request_clock(tmp_path)

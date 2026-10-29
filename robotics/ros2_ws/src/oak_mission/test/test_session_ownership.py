"""A launcher exit must not hide a live child; never signal a reused PID identity."""

import importlib.util
import signal
import subprocess
import sys
import time
from pathlib import Path


def ownership_module():
    path = Path(__file__).resolve().parents[5] / "scripts/robotics_session.py"
    spec = importlib.util.spec_from_file_location("session_ownership", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_exit_does_not_hide_termination_resistant_child(tmp_path):
    module = ownership_module()
    ready = tmp_path / "child-ready"
    child_code = (
        "import signal,time,pathlib,sys; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "signal.signal(signal.SIGINT,signal.SIG_IGN); "
        "pathlib.Path(sys.argv[1]).touch(); time.sleep(30)"
    )
    parent_code = (
        "import subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]); "
        "print(child.pid,flush=True); time.sleep(30)"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", parent_code, child_code, str(ready)],
        stdout=subprocess.PIPE,
        text=True,
    )
    owned = {}
    try:
        child_pid = int(parent.stdout.readline())
        deadline = time.monotonic() + 3
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        owned = module.descendant_identities([parent.pid])
        assert child_pid in owned
        module.signal_owned(owned, signal.SIGTERM)
        parent.wait(timeout=2)
        assert child_pid in module.live_owned(owned)
        assert module.kill_remaining_owned(owned, timeout=2) == {}
    finally:
        module.kill_remaining_owned(owned, timeout=2)
        if parent.poll() is None:
            parent.kill()
        parent.wait(timeout=2)


def test_mismatched_start_identity_is_never_signaled():
    module = ownership_module()
    child = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"])
    try:
        assert module.live_owned({child.pid: "impossible-start-time"}) == {}
        assert module.kill_remaining_owned({child.pid: "impossible-start-time"}) == {}
        assert child.poll() is None
    finally:
        child.kill()
        child.wait(timeout=2)

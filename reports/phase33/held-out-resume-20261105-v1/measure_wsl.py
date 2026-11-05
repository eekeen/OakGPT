import json
import os
import time
from pathlib import Path

out = Path("/mnt/d/Projects/OakGPT/runs/phase33/host-attribution-20261105-v1")
root = Path("/mnt/d/Projects/OakGPT/runs/phase33/held-out-replication-v1")
checks = []
for p in root.glob("*/*/STOPPED.json"):
    receipt = json.loads(p.read_text())
    live = []
    states = []
    for pid, start in receipt["owned_processes"].items():
        try:
            fields = Path("/proc", pid, "stat").read_text().rsplit(")", 1)[1].split()
            same = fields[19] == start
            states.append(
                dict(
                    pid=int(pid),
                    expected_start=start,
                    current_start=fields[19],
                    identity_matches=same,
                    state=fields[0],
                )
            )
            if same and fields[0] not in ["Z", "X"]:
                live.append(int(pid))
        except FileNotFoundError:
            states.append(dict(pid=int(pid), expected_start=start, state="absent"))
    checks.append(
        dict(
            receipt=str(p),
            recorded_cleanup_complete=receipt["cleanup_complete"],
            live_matching_owned=live,
            identities=states,
        )
    )
assert len(checks) == 2
(out / "owned_identity_check.json").write_text(json.dumps(checks, indent=2) + "\n")


def snapshot():
    rows = {}
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            raw = (p / "stat").read_text()
            parts = raw.rsplit(")", 1)[1].split()
            comm = raw.split("(", 1)[1].rsplit(")", 1)[0]
            args = (p / "cmdline").read_bytes().decode(errors="replace")
            category = (
                "oakgpt"
                if "OakGPT" in args or "/oak-phase" in args
                else "rlnav2"
                if "ROS2_RL_Navigation" in args or "rlnav2_" in args
                else "other"
            )
            rows[p.name] = dict(
                start=parts[19],
                ticks=int(parts[11]) + int(parts[12]),
                comm=comm,
                category=category,
                ppid=int(parts[1]),
            )
        except (OSError, ValueError, IndexError):
            pass
    return rows


samples = []
for _i in range(3):
    before = snapshot()
    t = time.monotonic()
    time.sleep(5)
    after = snapshot()
    elapsed = time.monotonic() - t
    rows = []
    for pid, x in after.items():
        if pid in before and before[pid]["start"] == x["start"]:
            rows.append(
                dict(
                    pid=int(pid),
                    start_ticks=x["start"],
                    comm=x["comm"],
                    category=x["category"],
                    cpu_core_equivalents=(x["ticks"] - before[pid]["ticks"])
                    / os.sysconf("SC_CLK_TCK")
                    / elapsed,
                )
            )
    samples.append(
        dict(
            interval_seconds=elapsed,
            processes=sorted(rows, key=lambda x: x["cpu_core_equivalents"], reverse=True),
            loadavg=Path("/proc/loadavg").read_text().strip(),
            cpu_pressure=Path("/proc/pressure/cpu").read_text().strip(),
            meminfo=Path("/proc/meminfo").read_text(),
        )
    )
(out / "wsl_resources.json").write_text(
    json.dumps(
        dict(
            samples=samples,
            limits="Current sampled processes only; historical load attribution is not proven",
        ),
        indent=2,
    )
    + "\n"
)
print(
    json.dumps(
        dict(
            owned_identity_matches_live=[x["live_matching_owned"] for x in checks],
            top_processes=[x["processes"][:5] for x in samples],
        ),
        indent=2,
    )
)

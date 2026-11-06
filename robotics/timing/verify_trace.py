"""Exercise native clock records and retain benchmark metrics in CTest output."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="oak-native-trace-") as directory:
    result = subprocess.check_output(
        [sys.argv[1]], env={**os.environ, "OAK_TIMING_DIR": directory}, text=True
    )
    stats = json.loads(result)
    records = [
        json.loads(line)
        for path in Path(directory).glob("*.jsonl")
        for line in path.read_text().splitlines()
    ]
    assert len(records) == stats["samples"] == 20000
    assert all(a["boot_ns"] <= b["boot_ns"] for a, b in zip(records, records[1:], strict=False))
    assert all(a["mono_ns"] <= b["mono_ns"] for a, b in zip(records, records[1:], strict=False))
    assert all(r["stage"] == "overhead_probe" for r in records)
    print(json.dumps({"native_clock_records_passed": len(records), "overhead": stats}))

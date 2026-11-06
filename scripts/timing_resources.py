"""Low-rate CPU-pressure and runnable-delay observations on the same Linux kernel."""

import json
import os
import threading
import time
from pathlib import Path


def start_resources(directory, roots):
    stopped = threading.Event()

    def sample():
        with (directory / "resources.jsonl").open("x", buffering=65536) as stream:
            while not stopped.wait(0.1):
                rows = []
                for pid in roots():
                    try:
                        rows.append(
                            {
                                "pid": pid,
                                "schedstat": Path(f"/proc/{pid}/schedstat").read_text().strip(),
                                "stat": Path(f"/proc/{pid}/stat").read_text().strip(),
                            }
                        )
                    except OSError:
                        continue
                stream.write(
                    json.dumps(
                        {
                            "boot_ns": time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                            "mono_ns": time.monotonic_ns(),
                            "cpu_pressure": Path("/proc/pressure/cpu").read_text(),
                            "loadavg": os.getloadavg(),
                            "processes": rows,
                        }
                    )
                    + "\n"
                )

    worker = threading.Thread(target=sample, name="timing-resource-observer")
    worker.start()
    return stopped, worker

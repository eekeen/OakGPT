"""Optional local timing records; disabled unless a native directory is supplied."""

import json
import math
import os
import time


class Timing:
    def __init__(self):
        root = os.environ.get("OAK_TIMING_DIR")
        self.errors = 0
        self.fd = None
        if root:
            try:
                self.fd = os.open(
                    os.path.join(root, f"python-{os.getpid()}.jsonl"),
                    os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                )
            except OSError:
                self.errors += 1

    def record(self, stage, **values):
        if self.fd is not None:
            values = {
                key: repr(value) if isinstance(value, float) and not math.isfinite(value) else value
                for key, value in values.items()
            }
            try:
                self._write(stage, values)
            except OSError:
                self.errors += 1

    def _write(self, stage, values):
        os.write(
            self.fd,
            (
                json.dumps(
                    {
                        "stage": stage,
                        "boot_ns": time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                        "mono_ns": time.monotonic_ns(),
                        "thread_cpu_ns": time.thread_time_ns(),
                        "pid": os.getpid(),
                        "trace_errors": self.errors,
                        **values,
                    },
                    allow_nan=False,
                )
                + "\n"
            ).encode(),
        )

"""Optional sampled device-wide VRAM; not falsely attributed to a model process."""

import subprocess
import threading


class VramSampler:
    def __init__(self, gpu_index: int | None = None, interval: float = 0.1) -> None:
        self.gpu_index = gpu_index
        self.interval = interval
        self.samples: list[int] = []
        self.error: str | None = None
        self.device_info: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        try:
            result = subprocess.check_output(
                [
                    "nvidia-smi",
                    f"--id={self.gpu_index}",
                    "--query-gpu=memory.used",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=5,
                stderr=subprocess.DEVNULL,
            )
            self.samples.append(int(result.strip()) * 1024 * 1024)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            self.error = str(exc)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._sample()
            if self.error:
                break

    def __enter__(self) -> "VramSampler":
        if self.gpu_index is not None:
            try:
                self.device_info = subprocess.check_output(
                    [
                        "nvidia-smi",
                        f"--id={self.gpu_index}",
                        "--query-gpu=name,driver_version,memory.total",
                        "--format=csv,noheader",
                    ],
                    text=True,
                    timeout=5,
                    stderr=subprocess.DEVNULL,
                ).strip()
            except (OSError, subprocess.SubprocessError) as exc:
                self.error = str(exc)
            self._sample()
            if not self.error:
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=6)

    def result(self) -> dict[str, object]:
        return {
            "scope": "device-wide sampled usage, including other processes",
            "gpu_index": self.gpu_index,
            "device_name_driver_total_memory": self.device_info,
            "requested_interval_s": self.interval,
            "samples": len(self.samples),
            "baseline_bytes": self.samples[0] if self.samples else None,
            "peak_bytes": max(self.samples) if self.samples else None,
            "error": self.error,
            "enabled": self.gpu_index is not None,
        }

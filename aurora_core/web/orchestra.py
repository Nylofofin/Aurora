from __future__ import annotations

from pathlib import Path
import os


def resource_worker_limit(task_count: int, *, load_per_cpu=None, available_ram=None,
                          cpu_count=None) -> int:
    """Bound concurrent read-only web workers using current host pressure."""
    task_count = max(0, int(task_count))
    if task_count < 2:
        return task_count
    cpu_count = max(1, int(cpu_count or os.cpu_count() or 1))
    if load_per_cpu is None:
        try:
            load_per_cpu = os.getloadavg()[0] / cpu_count
        except (AttributeError, OSError):
            load_per_cpu = 0.0
    if available_ram is None:
        try:
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                if line.startswith("MemAvailable:"):
                    available_ram = int(line.split()[1]) * 1024
                    break
        except (OSError, ValueError):
            available_ram = None
    if cpu_count <= 2 or load_per_cpu >= 0.90 or (available_ram is not None and available_ram < 2 * 1024**3):
        return 1
    if load_per_cpu >= 0.55 or (available_ram is not None and available_ram < 6 * 1024**3):
        return min(2, task_count)
    return min(3, task_count)

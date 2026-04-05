"""Simple in-process telemetry counters."""

from collections import defaultdict
from threading import Lock
from typing import Dict


class Metrics:
    def __init__(self):
        self._counts = defaultdict(int)
        self._lock = Lock()

    def increment(self, key: str, value: int = 1) -> None:
        with self._lock:
            self._counts[key] += value

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counts)


metrics = Metrics()

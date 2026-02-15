from __future__ import annotations
import csv
from pathlib import Path
from typing import Iterable

from .schemas import TelemetryRecord


class PassiveCSVLogger:
    """
    Passive only: write-only telemetry. Never read by agents.
    """
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, records: Iterable[TelemetryRecord]) -> None:
        exists = self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["t", "state", "stability", "mode", "event"])
            for r in records:
                w.writerow([r.t, r.state.value, f"{r.stability:.4f}", r.mode, r.event or ""])

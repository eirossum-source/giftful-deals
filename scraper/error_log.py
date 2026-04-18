from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


class ErrorLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.count = 0

    def error(self, msg: str) -> None:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        line = f"[{ts}] {msg}\n"
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        self.count += 1

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Iterable


class StateStore:
    """File-backed record of which units we've already alerted on.

    The on-disk shape is:
        {
            "<site>:<unit_id>": {
                "first_seen": <epoch>,
                "notified_at": <epoch>,
                "last_seen": <epoch>
            },
            ...
        }
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except json.JSONDecodeError:
                self._data = {}

    def _save(self) -> None:
        # Atomic write so a crash mid-write can't corrupt state.
        tmp = tempfile.NamedTemporaryFile(
            "w", delete=False, dir=str(self.path.parent or "."), suffix=".tmp"
        )
        try:
            json.dump(self._data, tmp, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        os.replace(tmp.name, self.path)

    def already_notified(self, key: str) -> bool:
        return key in self._data and self._data[key].get("notified_at") is not None

    def mark_seen(self, keys: Iterable[str]) -> None:
        now = time.time()
        for k in keys:
            entry = self._data.setdefault(k, {"first_seen": now})
            entry["last_seen"] = now
        self._save()

    def mark_notified(self, key: str) -> None:
        now = time.time()
        entry = self._data.setdefault(key, {"first_seen": now})
        entry["notified_at"] = now
        entry["last_seen"] = now
        self._save()

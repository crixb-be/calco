from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class HistoryManager:
    """Small, crash-tolerant JSON history capped at the latest 100 tasks."""

    MAX_RECORDS = 100

    def __init__(self, path: Path | None = None):
        self.path = path or self.default_path()
        self._lock = threading.RLock()

    @staticmethod
    def default_path() -> Path:
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "DocForge" / "history.json"
        return Path("data") / "history.json"

    def _read(self) -> list[dict[str, Any]]:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read()

    def record(
        self,
        *,
        task_id: str,
        task_type: str,
        source_name: str,
        target_path: str,
        status: str,
        duration_ms: int,
    ) -> dict[str, Any]:
        item = {
            "id": task_id,
            "type": task_type,
            "source_name": source_name,
            "target_path": target_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "duration_ms": max(0, int(duration_ms)),
        }
        with self._lock:
            records = (self._read() + [item])[-self.MAX_RECORDS:]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_name(f".{self.path.name}.tmp")
            try:
                with temp.open("w", encoding="utf-8", newline="\n") as handle:
                    json.dump(records, handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, self.path)
            finally:
                if temp.exists():
                    temp.unlink()
        return item

    def clear(self) -> None:
        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


_manager: HistoryManager | None = None
_manager_lock = threading.Lock()


def get_history_manager() -> HistoryManager:
    """Return the process-wide history manager used by tasks and RPCs."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = HistoryManager()
        return _manager

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from typing import Any

from .errors import EngineError


def action(name: str | None = None):
    def decorate(fn: Callable[..., Any]):
        setattr(fn, "__docforge_action__", name or fn.__name__)
        return fn
    return decorate


class ProgressReporter:
    def __init__(self, task_id: str, emit: Callable[[dict[str, Any]], None], cancel: threading.Event):
        self.task_id, self.emit, self.cancel = task_id, emit, cancel

    def report(self, percent: float, message: str | None = None) -> None:
        if self.cancel.is_set():
            raise EngineError("CANCELLED", "Task cancelled")
        event: dict[str, Any] = {"type": "progress", "id": self.task_id, "percent": max(0, min(100, percent))}
        if message:
            event["message"] = message
        self.emit(event)

    def log(self, message: str, level: str = "info") -> None:
        """Diagnostic step: to stderr (Tauri console, '[docforge-engine]' prefix) and as a
        'log' event (job log panel in the UI). Never printed to stdout: stdout is the NDJSON channel."""
        print(f"[{self.task_id}] {level.upper()} {message}", file=sys.stderr, flush=True)
        self.emit({"type": "log", "id": self.task_id, "level": level, "message": message})

    def check_cancelled(self) -> None:
        if self.cancel.is_set():
            raise EngineError("CANCELLED", "Task cancelled")


class BaseProcessor:
    engine_name = ""

    @classmethod
    def actions(cls) -> dict[str, Callable[..., Any]]:
        result: dict[str, Callable[..., Any]] = {}
        for klass in reversed(cls.mro()):
            for attr in klass.__dict__.values():
                name = getattr(attr, "__docforge_action__", None)
                if name:
                    result[name] = attr
        return result

    def execute(self, action_name: str, task, reporter: ProgressReporter):
        handler = self.actions().get(action_name)
        if handler is None:
            raise EngineError("UNKNOWN_ACTION", f"Unknown action '{self.engine_name}.{action_name}'")
        return handler(self, task, reporter)

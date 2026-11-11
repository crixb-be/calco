from __future__ import annotations

from typing import Literal

ErrorCode = Literal[
    "INVALID_TASK", "UNKNOWN_ACTION", "INPUT_NOT_FOUND", "WRONG_PASSWORD",
    "DEPENDENCY_MISSING", "BINARY_NOT_FOUND", "CANCELLED", "TIMEOUT", "CONVERSION_FAILED", "INTERNAL",
]


class EngineError(Exception):
    def __init__(self, code: ErrorCode, message: str, details: str | None = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details

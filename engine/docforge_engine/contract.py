from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ProcessorTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    engine: Literal["stirling_core", "docling_core", "office_bridge", "ffmpeg_bridge"]
    action: str = Field(min_length=1)
    inputFiles: list[str] = Field(default_factory=list)
    outputDir: str = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class ProgressEvent(BaseModel):
    type: Literal["progress"] = "progress"
    id: str
    percent: float
    message: str | None = None


class LogEvent(BaseModel):
    type: Literal["log"] = "log"
    id: str
    level: Literal["info", "warn", "error"]
    message: str


class ResultEvent(BaseModel):
    type: Literal["result"] = "result"
    id: str
    status: Literal["success"] = "success"
    outputFiles: list[str]
    meta: dict[str, Any] | None = None


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    id: str
    code: str
    message: str
    details: str | None = None


def parse_task(raw: str | dict[str, Any]) -> ProcessorTask:
    try:
        return ProcessorTask.model_validate_json(raw) if isinstance(raw, str) else ProcessorTask.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

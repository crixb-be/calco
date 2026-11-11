"""Request/response methods for the UI (ARCHITECTURE.md §6.1–6.2).

Fast queries (thumbnails, file reads) that must not wait behind long tasks in the job queue.
Each method takes a params dict and returns a JSON-serialisable dict, or raises EngineError.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Callable

from .errors import EngineError
from .core.cleanup import purge_temp_artifacts
from .util.thumbnail_generator import get_service
from .processors.stirling_core.page_organizer import render_page_thumbnails
from .storage.history_manager import HistoryManager

READABLE_EXTENSIONS = {".md", ".json", ".html", ".htm", ".txt", ".doctags"}
DEFAULT_MAX_BYTES = 20 * 1024 * 1024

RpcMethod = Callable[[dict[str, Any]], dict[str, Any]]
METHODS: dict[str, RpcMethod] = {}


def rpc_method(name: str):
    def decorate(fn: RpcMethod) -> RpcMethod:
        METHODS[name] = fn
        return fn

    return decorate


def _abs_path(params: dict[str, Any], key: str, must_exist: bool = True) -> Path:
    raw = params.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise EngineError("INVALID_TASK", f"Falta el parámetro '{key}'")
    path = Path(raw)
    if not path.is_absolute():
        raise EngineError("INVALID_TASK", f"'{key}' debe ser una ruta absoluta: {raw}")
    path = Path(os.path.abspath(path))
    if must_exist and not path.is_file():
        raise EngineError("INPUT_NOT_FOUND", f"Archivo no encontrado: {path}")
    return path


def _int(params: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(params.get(key, default))
    except (TypeError, ValueError) as exc:
        raise EngineError("INVALID_TASK", f"'{key}' debe ser un entero") from exc


@rpc_method("get_pdf_pages_metadata")
def get_pdf_pages_metadata(params: dict[str, Any]) -> dict[str, Any]:
    pdf = _abs_path(params, "pdfPath")
    return get_service().metadata(str(pdf), params.get("password"))


@rpc_method("get_page_thumbnails")
def get_page_thumbnails(params: dict[str, Any]) -> dict[str, Any]:
    pdf = _abs_path(params, "pdfPath")
    images = get_service().thumbnails(
        str(pdf),
        start=_int(params, "start", 0),
        count=_int(params, "count", 12),
        max_width=_int(params, "maxWidth", 300),
        fmt=str(params.get("format", "webp")),
        password=params.get("password"),
        tier=params.get("tier"),
    )
    return {"pages": [
        {"index": i["index"], "thumbUrl": i["url"], "width": i["width"], "height": i["height"], "dpi": i["dpi"], "tier": i["tier"]}
        for i in images
    ]}


@rpc_method("get_pdf_thumbnails")
def get_pdf_thumbnails(params: dict[str, Any]) -> dict[str, Any]:
    raw = params.get("source_pdf", params.get("pdfPath"))
    source = _abs_path({"path": raw}, "path")
    return {"pages": render_page_thumbnails(source), "dpi": 72}


@rpc_method("get_history")
def get_history(params: dict[str, Any]) -> dict[str, Any]:
    del params
    return {"records": HistoryManager().list()}


@rpc_method("clear_history")
def clear_history(params: dict[str, Any]) -> dict[str, Any]:
    del params
    HistoryManager().clear()
    return {"records": []}


@rpc_method("clear_temp_cache")
def clear_temp_cache(params: dict[str, Any]) -> dict[str, Any]:
    del params
    return {"removed": purge_temp_artifacts()}


@rpc_method("render_page")
def render_page(params: dict[str, Any]) -> dict[str, Any]:
    pdf = _abs_path(params, "pdfPath")
    image = get_service().image(
        str(pdf),
        _int(params, "index", 0),
        max_width=_int(params, "maxWidth", 1100),
        fmt=str(params.get("format", "webp")),
        password=params.get("password"),
        tier=params.get("tier"),
    )
    return {"index": image["index"], "imageUrl": image["url"], "width": image["width"], "height": image["height"],
            "dpi": image["dpi"], "tier": image["tier"]}


@rpc_method("read_text_file")
def read_text_file(params: dict[str, Any]) -> dict[str, Any]:
    path = _abs_path(params, "path")
    if path.suffix.lower() not in READABLE_EXTENSIONS:
        raise EngineError("INVALID_TASK", f"Extensión no permitida para lectura: {path.suffix or '(sin extensión)'}")
    max_bytes = _int(params, "maxBytes", DEFAULT_MAX_BYTES)
    size = path.stat().st_size
    if size > max_bytes:
        raise EngineError("INVALID_TASK", f"Archivo demasiado grande ({size} bytes > {max_bytes})")
    content = path.read_bytes().decode("utf-8", errors="replace")
    return {"content": content, "size": size}


@rpc_method("export_file")
def export_file(params: dict[str, Any]) -> dict[str, Any]:
    source = _abs_path(params, "sourcePath")
    target = _abs_path(params, "targetPath", must_exist=False)
    if os.path.normcase(str(source)) == os.path.normcase(str(target)):
        return {"path": str(target)}
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.docforge-tmp")
    shutil.copyfile(source, temp)
    os.replace(temp, target)
    return {"path": str(target)}


def dispatch(method: str, params: dict[str, Any] | None) -> dict[str, Any]:
    handler = METHODS.get(method)
    if handler is None:
        raise EngineError("UNKNOWN_ACTION", f"Método RPC desconocido: {method}")
    if params is not None and not isinstance(params, dict):
        raise EngineError("INVALID_TASK", "params debe ser un objeto")
    return handler(params or {})

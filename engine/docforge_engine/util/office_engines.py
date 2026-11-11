"""Shared Office-to-PDF engine selection and conversion cascade."""
from __future__ import annotations

import tempfile
from pathlib import Path

from ..errors import EngineError
from .binaries import _normalize as normalize_binary, locate_binary
from .office_com import OfficeComError, com_available, convert_with_office_com, office_kind_for_extension
from .paths import atomic_write_bytes, output_path, require_inputs, safe_stem
from .soffice_runner import DEFAULT_TIMEOUT_SEC, convert_with_soffice, neutral_temp_root


SUPPORTED_OFFICE_EXTENSIONS = frozenset({
    ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".odt", ".ods", ".odp", ".rtf", ".csv", ".txt",
})

NO_ENGINE_DETAILS = (
    "1) Instalar Microsoft Office (Word/Excel/PowerPoint) — se usa automáticamente.\n"
    "2) Instalar LibreOffice gratis desde https://www.libreoffice.org/download/\n"
    "3) Indicar la ruta de soffice.exe (o LibreOffice Portable) en Ajustes.\n"
    "4) Para PDF→Word existe fallback pdf2docx."
)


def detect_office_suites(binary_path: str | None = None) -> dict:
    """Per-suite availability for the Settings screen and ``health()``.

    ``binary_path`` is the LibreOffice path saved in Settings (may be empty). When it is
    set but invalid, auto-detection still runs and ``configuredInvalid`` flags the problem.
    """
    configured = (binary_path or "").strip()
    # Validate the configured path on its own: locate_binary would silently fall back.
    configured_path = normalize_binary("soffice", configured) if configured else None
    configured_valid = configured_path is not None
    libreoffice = str(configured_path) if configured_path else locate_binary("soffice", {})
    return {
        "msword": {"available": com_available("msword")},
        "msexcel": {"available": com_available("msexcel")},
        "mspowerpoint": {"available": com_available("mspowerpoint")},
        "libreoffice": {
            "available": libreoffice is not None,
            "path": libreoffice,
            "source": ("configured" if configured_valid else "auto") if libreoffice else None,
            "configuredInvalid": bool(configured) and not configured_valid,
        },
    }


def _no_engine() -> EngineError:
    return EngineError(
        "BINARY_NOT_FOUND",
        "No hay ninguna suite ofimática disponible para convertir a PDF",
        NO_ENGINE_DETAILS,
    )


def convert_office_to_pdf(task, reporter):
    inputs = require_inputs(task)
    engine = str(task.options.get("officeEngine", "auto")).lower()
    if engine not in {"auto", "msoffice", "libreoffice"}:
        raise EngineError("INVALID_TASK", "officeEngine debe ser auto, msoffice o libreoffice")
    # Preserve a useful no-engine diagnostic even when an input extension is not in the
    # Office matrix.  There is no converter available in that situation either.
    if not locate_binary("soffice", task.options) and not any(
        kind and com_available(kind)
        for kind in (office_kind_for_extension(source.suffix) for source in inputs)
    ):
        raise _no_engine()
    unsupported = [source.suffix.lower() for source in inputs if source.suffix.lower() not in SUPPORTED_OFFICE_EXTENSIONS]
    if unsupported:
        raise EngineError("INVALID_TASK", f"Formato Office no soportado: {unsupported[0]}")

    timeout = float(task.options.get("timeoutSec") or DEFAULT_TIMEOUT_SEC)
    outputs: list[str] = []
    engines: list[str] = []
    total = len(inputs)
    for index, source in enumerate(inputs):
        kind = office_kind_for_extension(source.suffix)
        out = output_path(task, safe_stem(source), task.action, ".pdf", index if total > 1 else None)
        span = 100.0 / total
        base = index * span
        last_tick = [-1.0]

        def tick(elapsed, limit):
            if elapsed - last_tick[0] < 1.0:
                return
            last_tick[0] = elapsed
            reporter.report(base + span * 0.9 * min(elapsed / limit, 0.99), f"Convirtiendo {source.name} ({elapsed:.0f}s)")

        converted = None
        selected_engine = None
        com_error: OfficeComError | None = None
        if engine in {"auto", "msoffice"} and kind and com_available(kind):
            reporter.report(base + 1, f"Iniciando Microsoft Office para {source.name}")
            try:
                with tempfile.TemporaryDirectory(prefix="docforge-office-res-", dir=neutral_temp_root()) as temp:
                    converted = convert_with_office_com(
                        kind, source, Path(temp), timeout_sec=timeout,
                        on_tick=tick,
                        is_cancelled=reporter.cancel.is_set,
                        log=lambda message, level: reporter.log(message, level),
                    )
                    atomic_write_bytes(out, converted.read_bytes())
                selected_engine = kind
            except OfficeComError as exc:
                if engine == "msoffice":
                    raise EngineError("CONVERSION_FAILED", str(exc), "Microsoft Office no pudo abrir o convertir el documento.") from exc
                com_error = exc
                reporter.log(f"Microsoft Office no pudo convertir {source.name}; se probará LibreOffice: {exc}", "warn")
            # Cancellation, timeout and input errors are intentional task outcomes, not fallback cases.
        elif engine == "msoffice":
            raise EngineError("BINARY_NOT_FOUND", f"Microsoft Office no está disponible para {source.suffix.lower()}")

        if converted is None:
            binary = locate_binary("soffice", task.options)
            if not binary:
                if com_error is not None:
                    # Office exists but could not handle this file: say so instead of
                    # claiming that no office suite is installed.
                    raise EngineError(
                        "CONVERSION_FAILED",
                        str(com_error),
                        "Comprueba que el documento no esté dañado ni protegido con contraseña.\n"
                        "Como alternativa, instala LibreOffice (https://www.libreoffice.org/download/) "
                        "o indica la ruta de soffice.exe en Ajustes para usarlo como respaldo.",
                    ) from com_error
                raise _no_engine()
            reporter.report(base + 1, f"Iniciando LibreOffice para {source.name}")
            reporter.log(f"LibreOffice detectado: {binary}")
            with tempfile.TemporaryDirectory(prefix="docforge-office-res-", dir=neutral_temp_root()) as temp:
                generated = convert_with_soffice(
                    binary, source, Path(temp), "pdf", timeout_sec=timeout,
                    on_tick=tick, is_cancelled=reporter.cancel.is_set,
                    log=lambda message, level: reporter.log(message, level),
                )
                atomic_write_bytes(out, generated.read_bytes())
            selected_engine = "libreoffice"

        outputs.append(str(out))
        engines.append(selected_engine or "libreoffice")
        reporter.report(base + span, f"Convertido {source.name}")
    metadata = {"engine": engines[0] if len(set(engines)) == 1 else engines, "count": len(outputs)}
    if engines == ["libreoffice"] or "libreoffice" in engines:
        metadata["binary"] = locate_binary("soffice", task.options)
    return outputs, metadata

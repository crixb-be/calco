"""Universal Office-to-PDF conversion facade.

The actual process runner lives in ``util.soffice_runner`` because the Office bridge
also uses it for PDF-to-Office fallbacks. Keeping this facade here makes the universal
processor contract explicit and exposes the supported input matrix in one place.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.binaries import locate_binary
from ...util.paths import atomic_write_bytes, output_path, require_inputs, safe_stem
from ...util.soffice_runner import DEFAULT_TIMEOUT_SEC, convert_with_soffice, neutral_temp_root


SUPPORTED_OFFICE_EXTENSIONS = frozenset({
    ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".odt", ".ods", ".odp", ".rtf", ".csv", ".txt",
})


def detect_libreoffice(options: dict | None = None) -> str | None:
    """Find soffice.exe in options, PATH, or standard Windows install locations."""
    return locate_binary("soffice", options or {})


class OfficeConverterProcessor(BaseProcessor):
    """Standalone universal action; the registry keeps the richer OfficeProcessor."""

    engine_name = "office_bridge"

    @action()
    def office_to_pdf(self, task, reporter):
        binary = detect_libreoffice(task.options)
        if not binary:
            raise EngineError("BINARY_NOT_FOUND", "LibreOffice (soffice.exe) no encontrado")
        inputs = require_inputs(task)
        outputs = []
        for index, source in enumerate(inputs):
            if source.suffix.lower() not in SUPPORTED_OFFICE_EXTENSIONS:
                raise EngineError("INVALID_TASK", f"Formato Office no soportado: {source.suffix}")
            output = output_path(task, safe_stem(source), "office_to_pdf", ".pdf", index if len(inputs) > 1 else None)
            with tempfile.TemporaryDirectory(prefix="docforge-office-", dir=neutral_temp_root()) as temp:
                generated = convert_with_soffice(
                    binary, source, Path(temp), "pdf",
                    timeout_sec=float(task.options.get("timeoutSec") or DEFAULT_TIMEOUT_SEC),
                    is_cancelled=reporter.cancel.is_set,
                    log=lambda message, level: reporter.log(message, level),
                )
                atomic_write_bytes(output, generated.read_bytes())
            reporter.report((index + 1) * 100 / len(inputs), f"Converted {source.name}")
            outputs.append(str(output))
        return outputs, {"binary": binary, "count": len(outputs)}

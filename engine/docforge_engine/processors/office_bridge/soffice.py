from __future__ import annotations

import os
import tempfile
from pathlib import Path

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.binaries import locate_binary
from ...util.soffice_runner import DEFAULT_TIMEOUT_SEC, convert_with_soffice, neutral_temp_root
from ...util.paths import atomic_write_bytes, output_path, require_inputs, safe_stem
from ..universal.office_converter import SUPPORTED_OFFICE_EXTENSIONS


class OfficeProcessor(BaseProcessor):
    engine_name = "office_bridge"

    def health(self):
        binary = locate_binary("soffice", {})
        return {"available": binary is not None, "binary": binary, "reason": None if binary else "LibreOffice not found"}

    def _run_soffice(self, task, source: Path, convert_to: str, reporter, *, index=0, total=1, infilter=None):
        binary = locate_binary("soffice", task.options)
        if not binary:
            raise EngineError(
                "BINARY_NOT_FOUND",
                "LibreOffice (soffice) no encontrado",
                "Instala LibreOffice o indica la ruta de soffice.exe en Ajustes "
                r"(p. ej. C:\Program Files\LibreOffice\program\soffice.exe).",
            )
        source = Path(os.path.abspath(source))
        output_dir = Path(os.path.abspath(task.outputDir))
        target_ext = convert_to.split(":", 1)[0]
        timeout = float(task.options.get("timeoutSec") or DEFAULT_TIMEOUT_SEC)
        span = 100.0 / total
        base = index * span
        reporter.log(f"LibreOffice detectado: {binary}")
        reporter.log(f"Destino: {output_dir}")
        reporter.report(base + 1, f"Iniciando LibreOffice para {source.name}")

        last_tick = [-1.0]

        def tick(elapsed, limit):
            # Heartbeat (max 1/s): progress within this file's slice, so the UI never sits at 0%.
            if elapsed - last_tick[0] < 1.0:
                return
            last_tick[0] = elapsed
            reporter.report(base + span * 0.9 * min(elapsed / limit, 0.99), f"Convirtiendo {source.name} ({elapsed:.0f}s)")

        out = output_path(task, safe_stem(source), task.action, f".{target_ext}")
        # LibreOffice works in a neutral ASCII temp dir; the result is then written atomically to
        # the final (possibly accented) path, never clobbering an existing file.
        with tempfile.TemporaryDirectory(prefix="docforge-res-", dir=neutral_temp_root()) as temp_dir:
            generated = convert_with_soffice(
                binary, source, Path(temp_dir), convert_to,
                infilter=infilter, timeout_sec=timeout, on_tick=tick,
                is_cancelled=reporter.cancel.is_set, log=lambda msg, level: reporter.log(msg, level),
            )
            atomic_write_bytes(out, generated.read_bytes())
        reporter.log(f"Archivo final: {out}")
        reporter.report(base + span, f"Convertido {source.name}")
        return str(out)

    @action()
    def office_to_pdf(self, task, reporter):
        if not locate_binary("soffice", task.options):
            raise EngineError(
                "BINARY_NOT_FOUND",
                "LibreOffice (soffice) no encontrado",
                "Instala LibreOffice o indica la ruta de soffice.exe en Ajustes.",
            )
        inputs = require_inputs(task)
        unsupported = [source.suffix.lower() for source in inputs if source.suffix.lower() not in SUPPORTED_OFFICE_EXTENSIONS]
        if unsupported:
            raise EngineError("INVALID_TASK", f"Formato Office no soportado: {unsupported[0]}")
        outputs = [self._run_soffice(task, source, "pdf", reporter, index=i, total=len(inputs)) for i, source in enumerate(inputs)]
        return outputs, {"binary": locate_binary("soffice", task.options)}

    @action()
    def pdf_to_docx(self, task, reporter):
        inputs = require_inputs(task)
        binary = locate_binary("soffice", task.options)
        if binary:
            outputs = [
                self._run_soffice(task, source, "docx:MS Word 2007 XML", reporter, index=i, total=len(inputs), infilter="writer_pdf_import")
                for i, source in enumerate(inputs)
            ]
            return outputs, {}
        try:
            from pdf2docx import Converter
        except ImportError as exc:
            raise EngineError("BINARY_NOT_FOUND", "LibreOffice was not found and pdf2docx is not installed", str(exc)) from exc
        outputs = []
        for source in inputs:
            out = output_path(task, safe_stem(source), "pdf_to_docx", ".docx")
            converter = Converter(str(source))
            try:
                converter.convert(str(out))
            finally:
                converter.close()
            outputs.append(str(out))
            reporter.report((len(outputs) / len(inputs)) * 100, f"Converted {source.name}")
        return outputs, {"fallback": "pdf2docx"}

    @action()
    def pdf_to_xlsx(self, task, reporter):
        try:
            import pymupdf
            from openpyxl import Workbook
        except ImportError as exc:
            raise EngineError("DEPENDENCY_MISSING", "PyMuPDF and openpyxl are required for pdf_to_xlsx", str(exc)) from exc
        inputs = require_inputs(task)
        outputs = []
        for source in inputs:
            doc = pymupdf.open(source)
            workbook = Workbook()
            workbook.remove(workbook.active)
            table_count = 0
            try:
                for page_no, page in enumerate(doc):
                    finder = page.find_tables()
                    tables = getattr(finder, "tables", [])
                    for table_no, table in enumerate(tables):
                        rows = table.extract()
                        sheet = workbook.create_sheet(f"Page {page_no + 1}-{table_no + 1}")
                        for row in rows:
                            sheet.append(list(row))
                        table_count += 1
                    reporter.report((page_no + 1) * 100 / len(doc), f"Detected tables on page {page_no + 1}")
                if table_count == 0:
                    sheet = workbook.create_sheet("Extracted text")
                    for page in doc:
                        for line in page.get_text("text").splitlines():
                            if line.strip():
                                sheet.append([line])
                out = output_path(task, safe_stem(source), "pdf_to_xlsx", ".xlsx")
                from ...util.paths import atomic_save
                atomic_save(out, lambda temp: workbook.save(temp))
                outputs.append(str(out))
            finally:
                doc.close()
        return outputs, {"tables": table_count}

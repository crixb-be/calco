"""Visual PDF page thumbnails and single-document page layout operations."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.paths import atomic_save, output_path, safe_stem
from .common import one_input, pymupdf_module


def _rotation(value: Any) -> int:
    try:
        degrees = int(value)
    except (TypeError, ValueError) as exc:
        raise EngineError("INVALID_TASK", f"rotation must be a multiple of 90: {value!r}") from exc
    if degrees % 90:
        raise EngineError("INVALID_TASK", f"rotation must be a multiple of 90: {degrees}")
    return degrees % 360


def render_page_thumbnails(source: Path) -> list[dict[str, Any]]:
    """Render all pages at 72 DPI without retaining PyMuPDF objects after return."""
    pymupdf = pymupdf_module()
    document = pymupdf.open(str(source))
    try:
        pages = []
        for index, page in enumerate(document):
            pix = page.get_pixmap(dpi=72, alpha=False)
            encoded = base64.b64encode(pix.tobytes("png")).decode("ascii")
            pages.append({
                "page_index": index,
                "page_number": index + 1,
                "rotation": int(page.rotation),
                "thumbnail": f"data:image/png;base64,{encoded}",
                "width": pix.width,
                "height": pix.height,
            })
        return pages
    finally:
        document.close()


class PdfPageOrganizerProcessor(BaseProcessor):
    engine_name = "stirling_core"

    @action()
    def get_pdf_thumbnails(self, task, reporter):
        source = one_input(task)
        reporter.report(0, "Renderizando miniaturas…")
        pages = render_page_thumbnails(source)
        for index in range(len(pages)):
            reporter.check_cancelled()
            reporter.report((index + 1) * 100 / max(1, len(pages)), f"Miniatura {index + 1}/{len(pages)}")
        return [], {"pages": pages, "dpi": 72}

    @action()
    def apply_page_layout(self, task, reporter):
        pymupdf = pymupdf_module()
        raw_source = task.options.get("source_pdf") or task.options.get("sourcePdf")
        source = Path(raw_source) if raw_source else one_input(task)
        source = source.expanduser().absolute()
        if not source.is_file():
            raise EngineError("INPUT_NOT_FOUND", f"PDF no encontrado: {source}")
        raw_pages = task.options.get("pages")
        if not isinstance(raw_pages, list) or not raw_pages:
            raise EngineError("INVALID_TASK", "apply_page_layout.pages debe ser una lista no vacía")

        document = pymupdf.open(str(source))
        result = pymupdf.open()
        try:
            normalized: list[tuple[int, int]] = []
            for item in raw_pages:
                if not isinstance(item, dict):
                    raise EngineError("INVALID_TASK", "Cada página debe ser un objeto")
                try:
                    page_index = int(item["page_index"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise EngineError("INVALID_TASK", "Cada página requiere page_index entero") from exc
                if not 0 <= page_index < document.page_count:
                    raise EngineError("INVALID_TASK", f"page_index fuera de rango: {page_index}")
                normalized.append((page_index, _rotation(item.get("rotation", 0))))

            for index, (page_index, extra_rotation) in enumerate(normalized):
                reporter.check_cancelled()
                result.insert_pdf(document, from_page=page_index, to_page=page_index, links=True, annots=True)
                page = result[-1]
                page.set_rotation((int(document[page_index].rotation) + extra_rotation) % 360)
                reporter.report((index + 1) * 100 / len(normalized), f"Página {index + 1}/{len(normalized)}")

            out = output_path(task, safe_stem(source), "apply_page_layout", ".pdf")
            atomic_save(out, lambda temp: result.save(temp, garbage=4, deflate=True))
            return [str(out)], {"pages": len(normalized)}
        finally:
            result.close()
            document.close()

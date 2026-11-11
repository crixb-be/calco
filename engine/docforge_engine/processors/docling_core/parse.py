from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import re
from pathlib import Path

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.pages import page_ranges
from ...util.paths import atomic_write_bytes, output_path, require_inputs, safe_stem


def _load_docling():
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
        return DocumentConverter, PdfFormatOption, PdfPipelineOptions, InputFormat
    except ImportError as exc:
        raise EngineError("DEPENDENCY_MISSING", "Docling is not installed; install the docling extra", str(exc)) from exc


_NO_MODELS = {
    "with_layout": False,
    "with_tableformer": False,
    "with_code_formula": False,
    "with_picture_classifier": False,
    "with_rapidocr": False,
    "with_easyocr": False,
}


SUPPORTED_FORMATS = ("md", "json", "html", "doctags")


def normalize_formats(raw) -> tuple[list[str], list[str]]:
    """Accept ``["md", "json"]``, ``"md\\njson"``, ``"md, json"`` or nested mixes.

    Returns ``(formats, ignored)``: unique supported formats in request order (``["md"]`` when
    nothing valid remains) plus the unsupported tokens that were dropped."""
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    tokens: list[str] = []
    for item in items:
        if item is None:
            continue
        tokens.extend(part.strip().lower().lstrip(".") for part in re.split(r"[\r\n,;]+", str(item)))
    tokens = [token for token in dict.fromkeys(tokens) if token]
    if "markdown" in tokens:
        tokens = ["md" if token == "markdown" else token for token in tokens]
    formats = [token for token in dict.fromkeys(tokens) if token in SUPPORTED_FORMATS]
    ignored = [token for token in tokens if token not in SUPPORTED_FORMATS]
    return formats or ["md"], ignored


def normalize_page_selection(pages, total: int | None) -> tuple[tuple[int, int] | None, list[int] | None]:
    """Normalize the public page syntax into Docling's ``page_range``.

    Docling validates ``page_range`` as a strict ``(start, end)`` tuple (1-based, inclusive);
    a list fails Pydantic with ``tuple_type``. Returns ``(page_range, discrete_pages)``:
    - empty / ``None`` / whole document -> ``(None, None)`` (Docling's default range)
    - ``[start, end]`` or a contiguous selection -> ``((start, end), None)``
    - discrete pages ("1,3,5") -> ``((min, max), [1, 3, 5])``: the spanning tuple is converted
      and the exports are filtered per page afterwards.
    """
    if pages is None or pages == "" or (isinstance(pages, (list, tuple)) and len(pages) == 0):
        return None, None
    if (
        isinstance(pages, (list, tuple))
        and len(pages) == 2
        and all(isinstance(x, int) and not isinstance(x, bool) for x in pages)
        and 0 < pages[0] <= pages[1]
        and (total is None or pages[1] <= total)
    ):
        return (int(pages[0]), int(pages[1])), None
    if total is None:
        return None, None
    selected = sorted(index + 1 for index in page_ranges(pages, total))
    if not selected or selected == list(range(1, total + 1)):
        return None, None
    span = (selected[0], selected[-1])
    contiguous = selected == list(range(span[0], span[1] + 1))
    return span, (None if contiguous else selected)


def _only_pages(document, pages: list[int] | None):
    """Return ``document`` restricted to ``pages`` (discrete selections like "1,3").

    Docling converts the spanning range (1-3), so whole-document exporters (JSON, DocTags)
    would otherwise include the unselected pages in between."""
    if not pages:
        return document
    keep = set(pages) & set(document.pages.keys())
    if not keep or keep == set(document.pages.keys()):
        return document
    filtered = getattr(document, "filter", None)
    if filtered is None:
        raise EngineError("DEPENDENCY_MISSING", "Installed docling-core cannot filter pages; update docling-core")
    return filtered(page_nrs=keep)


def _shift_pages(data: dict, offset: int) -> None:
    """Undo ``DoclingDocument.filter`` renumbering (it rebases page 3 of "3,5" to page 1) so
    the exported JSON keeps the source PDF's page numbers in ``pages`` and every ``prov``."""
    if not offset:
        return
    pages = data.get("pages")
    if isinstance(pages, dict):
        shifted = {}
        for key, page in pages.items():
            number = int(key) + offset
            if isinstance(page, dict) and "page_no" in page:
                page["page_no"] = number
            shifted[str(number)] = page
        data["pages"] = shifted

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "prov" and isinstance(value, list):
                    for prov in value:
                        if isinstance(prov, dict) and isinstance(prov.get("page_no"), int):
                            prov["page_no"] += offset
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for key, value in data.items():
        if key != "pages":
            walk(value)


class DoclingProcessor(BaseProcessor):
    engine_name = "docling_core"

    def health(self):
        try:
            available = importlib.util.find_spec("docling") is not None
        except Exception:
            available = False
        return {"available": available, "version": "lazy" if available else None, "reason": None if available else "docling not installed"}

    @staticmethod
    def artifacts_path() -> Path:
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        path = Path(os.path.abspath(appdata / "DocForge" / "models"))
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _model_groups(*, ocr: bool, tables: bool, formulas: bool) -> list[tuple[str, dict]]:
        """Model groups the configured pipeline needs, as (label, download_models kwargs)."""
        groups: list[tuple[str, dict]] = [("modelo de layout", {**_NO_MODELS, "with_layout": True})]
        if tables:
            groups.append(("modelo de tablas (TableFormer)", {**_NO_MODELS, "with_tableformer": True}))
        if ocr:
            if importlib.util.find_spec("rapidocr") is not None:
                groups.append(("modelos de OCR (RapidOCR)", {**_NO_MODELS, "with_rapidocr": True}))
            elif importlib.util.find_spec("easyocr") is not None:
                groups.append(("modelos de OCR (EasyOCR)", {**_NO_MODELS, "with_easyocr": True}))
        if formulas:
            groups.append(("modelo de fórmulas LaTeX (puede tardar, ~1 GB)", {**_NO_MODELS, "with_code_formula": True}))
        return groups

    @staticmethod
    def _ensure_models(reporter, groups, start: float, end: float, artifacts: Path) -> None:
        """Download (or verify) each model group into ``artifacts``, reporting start..end percent.

        Hugging Face gives no progress callback, so we report before each group: the UI names
        the model being fetched instead of sitting silently at 0 %."""
        try:
            from docling.utils.model_downloader import download_models
        except ImportError as exc:
            raise EngineError("DEPENDENCY_MISSING", "Docling model downloader unavailable", str(exc)) from exc
        step = (end - start) / max(1, len(groups))
        for index, (label, kwargs) in enumerate(groups):
            reporter.report(start + step * index, f"Verificando/descargando {label}...")
            reporter.log(f"Comprobando {label} en {artifacts}")
            try:
                download_models(output_dir=artifacts, progress=False, **kwargs)
            except Exception as exc:  # offline with a populated cache must still work
                reporter.log(f"No se pudo verificar {label}: {exc}. Se usará la caché local si existe.", "warn")
            reporter.check_cancelled()
        reporter.report(end, "Modelos de IA listos")

    @action()
    def prefetch_models(self, task, reporter):
        _load_docling()
        custom = task.options.get("artifactsPath")
        artifacts = Path(os.path.abspath(custom)) if custom else self.artifacts_path()
        artifacts.mkdir(parents=True, exist_ok=True)
        reporter.report(5, "Iniciando motor de IA...")
        groups = self._model_groups(ocr=True, tables=True, formulas=bool(task.options.get("formulas", True)))
        self._ensure_models(reporter, groups, 10, 99, artifacts)
        reporter.report(100, "Completado")
        return [], {"artifactsPath": str(artifacts)}

    @staticmethod
    def _page_count(source: Path) -> int | None:
        if source.suffix.lower() != ".pdf":
            return None
        try:
            import pymupdf
        except ImportError:
            return None
        document = pymupdf.open(str(source))
        try:
            return len(document)
        finally:
            document.close()

    @action()
    def docling_parse(self, task, reporter):
        reporter.report(5, "Iniciando motor de IA...")
        DocumentConverter, PdfFormatOption, PdfPipelineOptions, InputFormat = _load_docling()
        inputs = [path.resolve() for path in require_inputs(task)]
        options = task.options
        formats, invalid = normalize_formats(options.get("exportFormats"))
        if invalid:
            reporter.log(f"Formatos ignorados (no soportados): {', '.join(invalid)}", "warn")
        ocr = bool(options.get("ocr", False))
        formulas = bool(options.get("formulas", False))
        mode = str(options.get("tableMode", "fast")).lower()
        tables = mode in ("fast", "accurate")
        custom_artifacts = options.get("artifactsPath")
        artifacts = Path(os.path.abspath(custom_artifacts)) if custom_artifacts else self.artifacts_path()
        artifacts.mkdir(parents=True, exist_ok=True)
        # Validate page selections before any slow model work, so bad input fails at once.
        selections = [normalize_page_selection(options.get("pages"), self._page_count(source)) for source in inputs]

        reporter.report(15,"Verificando/descargando modelos de OCR y visión...")
        self._ensure_models(reporter, self._model_groups(ocr=ocr, tables=tables, formulas=formulas), 15, 45, artifacts)

        pipeline = PdfPipelineOptions()
        pipeline.do_ocr = ocr
        pipeline.do_table_structure = tables
        if hasattr(pipeline, "do_formula_enrichment"):
            pipeline.do_formula_enrichment = formulas
        if hasattr(pipeline, "artifacts_path"):
            pipeline.artifacts_path = str(artifacts)
        if tables:
            with contextlib.suppress(Exception):
                pipeline.table_structure_options.mode = mode
        converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline)})

        outputs: list[str] = []
        count = len(inputs)
        for input_no, source in enumerate(inputs):
            reporter.check_cancelled()
            base = 50 + 50 * input_no / count
            span = 50 / count
            suffix = f" ({input_no + 1}/{count})" if count > 1 else ""
            page_range, discrete = selections[input_no]
            reporter.report(base, f"Extrayendo estructura y tablas del documento{suffix}...")
            convert_kwargs = {"page_range": page_range} if page_range is not None else {}
            # Docling's image pipeline is registered by the default converter. Keep the
            # tuned PDF pipeline for PDFs and use the native image pipeline for scans/photos.
            active_converter = converter if source.suffix.lower() == ".pdf" else DocumentConverter()
            result = active_converter.convert(str(source), **convert_kwargs)
            reporter.check_cancelled()
            reporter.report(base + span * 0.7, f"Generando Markdown y fórmulas LaTeX{suffix}...")
            for fmt in formats:
                content, ext = self._export(result.document, fmt, discrete)
                out = output_path(task, safe_stem(source), "docling_parse", ext, len(outputs)).resolve()
                atomic_write_bytes(out, str(content).encode("utf-8"))
                outputs.append(str(out))
            reporter.report(base + span, f"Procesado {source.name}")
        reporter.report(100, "Completado")
        return outputs, {"formats": formats, "artifactsPath": str(artifacts)}

    @staticmethod
    def _export(document, fmt: str, pages: list[int] | None) -> tuple[str, str]:
        if fmt == "md":
            if pages:
                return "\n\n".join(document.export_to_markdown(page_no=page) for page in pages), ".md"
            return document.export_to_markdown(), ".md"
        if fmt == "json":
            data = _only_pages(document, pages).export_to_dict()
            if pages and document.pages:
                _shift_pages(data, min(document.pages.keys()) - 1)
            return json.dumps(data, ensure_ascii=False, indent=2), ".json"
        if fmt == "html":
            if pages:
                return "\n".join(document.export_to_html(page_no=page) for page in pages), ".html"
            return document.export_to_html(), ".html"
        exporter = getattr(_only_pages(document, pages), "export_to_doctags", None)
        if exporter is None:
            raise EngineError("DEPENDENCY_MISSING", "Installed Docling version has no doctags exporter")
        return exporter(), ".doctags"

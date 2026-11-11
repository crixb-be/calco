"""Render every page of a PDF to a raster image.

This module is intentionally independent from the legacy Stirling processor so the
universal converter and direct engine actions share exactly the same renderer.
"""
from __future__ import annotations

import io
from pathlib import Path

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.pages import page_ranges
from ...util.paths import atomic_write_bytes, output_path, safe_stem
from ..stirling_core.common import one_input, pymupdf_module
from .image_converter import encode, parse_quality, prepare_mode


FORMATS = {"png": "png", "jpg": "jpg", "jpeg": "jpg", "webp": "webp"}


def _webp_bytes(pix, quality: int) -> bytes:
    """Encode a PyMuPDF pixmap as WebP through Pillow (MuPDF has no WebP encoder)."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow is part of the PDF extra
        raise EngineError("DEPENDENCY_MISSING", "Pillow is required for WebP output", str(exc)) from exc
    mode = "RGBA" if pix.alpha else "RGB"
    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    return encode(prepare_mode(image, "WEBP"), "WEBP", quality)


def render_pdf_to_images(
    source: Path,
    output_dir: Path,
    *,
    dpi: int = 150,
    image_format: str = "png",
    quality=85,
    pages=None,
    stem: str | None = None,
    report=None,
    check_cancelled=None,
) -> list[Path]:
    """Render selected 1-based pages and return the generated paths."""
    pymupdf = pymupdf_module()
    fmt = FORMATS.get(str(image_format).lower().lstrip("."))
    if fmt is None:
        raise EngineError("INVALID_TASK", "pdf_to_images.format must be png, jpg, or webp")
    try:
        dpi = int(dpi)
    except (TypeError, ValueError) as exc:
        raise EngineError("INVALID_TASK", "dpi must be an integer between 36 and 600", str(dpi)) from exc
    if not 36 <= dpi <= 600:
        raise EngineError("INVALID_TASK", "dpi must be between 36 and 600")
    compression_quality = parse_quality(quality)
    source = Path(source).expanduser().absolute()
    output_dir = Path(output_dir).expanduser().absolute()
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open(str(source))
    try:
        selected = page_ranges(pages, len(doc))
        outputs: list[Path] = []
        for count, page_no in enumerate(selected):
            if check_cancelled:
                check_cancelled()
            pix = doc[page_no].get_pixmap(dpi=dpi, alpha=False)
            if fmt == "webp":
                data = _webp_bytes(pix, compression_quality)
            else:
                data = pix.tobytes(fmt, jpg_quality=compression_quality)
            output = output_dir / f"{safe_stem(Path(stem or source.stem))}_pdf_to_images_{count + 1}.{fmt}"
            # Avoid overwriting a previous task's result when the user reuses a folder.
            if output.exists():
                suffix = 2
                while output.exists():
                    output = output.with_name(f"{output.stem}_{suffix}{output.suffix}")
                    suffix += 1
            atomic_write_bytes(output, data)
            outputs.append(output)
            if report:
                report((count + 1) * 100 / max(1, len(selected)), f"Rendered page {page_no + 1}")
        return outputs
    finally:
        doc.close()


class PdfToImagesProcessor(BaseProcessor):
    engine_name = "stirling_core"

    @action()
    def pdf_to_images(self, task, reporter):
        source = one_input(task)
        outputs = render_pdf_to_images(
            source,
            Path(task.outputDir),
            dpi=task.options.get("dpi", 150),
            image_format=task.options.get("format", "png"),
            quality=task.options.get("quality", 85),
            pages=task.options.get("pages"),
            report=reporter.report,
            check_cancelled=reporter.check_cancelled,
        )
        return [str(path) for path in outputs], {"dpi": int(task.options.get("dpi", 150)), "count": len(outputs)}

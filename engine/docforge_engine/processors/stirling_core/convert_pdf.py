from __future__ import annotations

import html
from pathlib import Path

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.pages import page_ranges
from ...util.paths import atomic_write_bytes, output_path, require_inputs, safe_stem
from .common import fitz_module, one_input


class PdfConvertProcessor(BaseProcessor):
    engine_name = "stirling_core"

    @action()
    def pdf_to_images(self, task, reporter):
        # Kept as a direct compatibility entry point for integrations importing this
        # legacy processor. The registry uses the universal renderer implementation.
        from ..universal.pdf_to_images import render_pdf_to_images

        source = one_input(task)
        outputs = render_pdf_to_images(
            source, Path(task.outputDir), dpi=task.options.get("dpi", 150),
            image_format=task.options.get("format", "png"), quality=task.options.get("quality", 85),
            pages=task.options.get("pages"), report=reporter.report,
            check_cancelled=reporter.check_cancelled,
        )
        return [str(path) for path in outputs], {"dpi": int(task.options.get("dpi", 150))}

    @action()
    def extract_images(self, task, reporter):
        fitz = fitz_module()
        source = one_input(task)
        minimum = int(task.options.get("minSize", 0))
        doc = fitz.open(source)
        outputs = []
        seen = set()
        try:
            for page_no, page in enumerate(doc):
                for image in page.get_images(full=True):
                    xref = image[0]
                    if xref in seen:
                        continue
                    seen.add(xref)
                    data = doc.extract_image(xref)
                    if max(data.get("width", 0), data.get("height", 0), len(data.get("image", b""))) < minimum:
                        continue
                    ext = data.get("ext", "png")
                    out = output_path(task, safe_stem(source), "extract_images", f".{ext}", len(outputs))
                    atomic_write_bytes(out, data["image"])
                    outputs.append(str(out))
                reporter.report((page_no + 1) * 100 / len(doc), f"Scanned images on page {page_no + 1}")
            return outputs, {"count": len(outputs)}
        finally:
            doc.close()

    @action()
    def images_to_pdf(self, task, reporter):
        fitz = fitz_module()
        inputs = require_inputs(task)
        page_size = str(task.options.get("pageSize", "fit")).upper()
        margin = float(task.options.get("margin", 0))
        out_doc = fitz.open()
        try:
            for index, image_path in enumerate(inputs):
                reporter.check_cancelled()
                try:
                    image = fitz.Pixmap(str(image_path))
                    source = {"filename": str(image_path)}
                except Exception:
                    # MuPDF cannot decode some formats (e.g. WebP): decode with Pillow instead.
                    from ..universal.image_converter import load_rgb_png_bytes
                    try:
                        stream = load_rgb_png_bytes(image_path)
                    except Exception as exc:
                        raise EngineError("CONVERSION_FAILED", f"No se pudo leer {image_path.name}", f"{type(exc).__name__}: {exc}") from exc
                    image = fitz.Pixmap(stream)
                    source = {"stream": stream}
                if page_size == "A4":
                    width, height = 595.28, 841.89
                elif page_size == "LETTER":
                    width, height = 612, 792
                else:
                    width, height = float(image.width), float(image.height)
                page = out_doc.new_page(width=width, height=height)
                rect = fitz.Rect(margin, margin, width - margin, height - margin)
                page.insert_image(rect, keep_proportion=True, **source)
                reporter.report((index + 1) * 100 / len(inputs), f"Added image {index + 1}")
            out = output_path(task, safe_stem(inputs[0]), "images_to_pdf", ".pdf")
            from ...util.paths import atomic_save
            atomic_save(out, lambda temp: out_doc.save(temp, garbage=4, deflate=True))
            return [str(out)], {"pages": len(inputs)}
        finally:
            out_doc.close()

    @action()
    def pdf_to_html(self, task, reporter):
        fitz = fitz_module()
        source = one_input(task)
        doc = fitz.open(source)
        try:
            pieces = ["<!doctype html><html><head><meta charset='utf-8'><title>DocForge PDF</title></head><body>"]
            for number, page in enumerate(doc):
                pieces.append(f"<section data-page='{number + 1}'>{page.get_text('html')}</section>")
                reporter.report((number + 1) * 100 / len(doc), f"Converted page {number + 1}")
            pieces.append("</body></html>")
            out = output_path(task, safe_stem(source), "pdf_to_html", ".html")
            atomic_write_bytes(out, "\n".join(pieces).encode("utf-8"))
            return [str(out)], {"pages": len(doc)}
        finally:
            doc.close()

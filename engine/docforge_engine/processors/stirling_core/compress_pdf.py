from __future__ import annotations

from pathlib import Path

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.paths import atomic_save, output_path, safe_stem
from .common import one_input, pymupdf_module


class PdfCompressionProcessor(BaseProcessor):
    engine_name = "stirling_core"

    @action()
    def compress_pdf(self, task, reporter):
        pymupdf = pymupdf_module()
        source = one_input(task)
        try:
            quality = int(task.options.get("quality", 75))
        except (TypeError, ValueError) as exc:
            raise EngineError("INVALID_TASK", "compress_pdf.quality must be between 1 and 100", str(task.options.get("quality"))) from exc
        if not 1 <= quality <= 100:
            raise EngineError("INVALID_TASK", "compress_pdf.quality must be between 1 and 100")
        output = output_path(task, safe_stem(source), "compress_pdf", ".pdf")
        document = pymupdf.open(str(source))
        try:
            # Re-encode eligible embedded images before the final garbage/stream pass.
            document.rewrite_images(
                dpi_threshold=int(task.options.get("dpiThreshold", 200)),
                dpi_target=int(task.options.get("dpiTarget", 150)),
                quality=quality,
                lossy=quality < 100,
                lossless=True,
                bitonal=True,
                color=True,
                gray=True,
            )
            reporter.report(35, "Optimizing embedded images")
            reporter.check_cancelled()
            atomic_save(
                output,
                lambda temp: document.save(
                    temp,
                    garbage=4,
                    clean=1,
                    deflate=1,
                    deflate_images=1,
                    deflate_fonts=1,
                    use_objstms=1,
                    compression_effort=100,
                ),
            )
            reporter.report(100, "PDF compressed")
        finally:
            document.close()
        return [str(output)], {"quality": quality, "inputBytes": source.stat().st_size, "outputBytes": output.stat().st_size}

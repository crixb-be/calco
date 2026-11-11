from __future__ import annotations

import re
from pathlib import Path

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.pages import page_ranges
from ...util.paths import atomic_save, output_path, safe_stem
from .common import fitz_module, one_input


PRESETS = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "phone": r"(?<!\d)(?:\+?\d[\d ()-]{6,}\d)(?!\d)",
    "dni": r"(?<!\d)\d{8}(?!\d)",
    "iban": r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b",
    "card": r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)",
}


class PdfEditProcessor(BaseProcessor):
    engine_name = "stirling_core"

    @action()
    def redact(self, task, reporter):
        fitz = fitz_module()
        source = one_input(task)
        doc = fitz.open(source)
        try:
            terms = [str(term) for term in task.options.get("terms", [])]
            patterns = [re.compile(str(pattern), re.IGNORECASE) for pattern in task.options.get("regex", [])]
            patterns += [re.compile(PRESETS[name], re.IGNORECASE) for name in task.options.get("presets", []) if name in PRESETS]
            areas = task.options.get("areas", []) or []
            selected = set(page_ranges(task.options.get("pages"), len(doc))) if task.options.get("pages") is not None else set(range(len(doc)))
            for number, page in enumerate(doc):
                if number not in selected:
                    continue
                rects = []
                for term in terms:
                    rects.extend(page.search_for(term))
                if patterns:
                    for block in page.get_text("dict").get("blocks", []):
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                if any(pattern.search(span.get("text", "")) for pattern in patterns):
                                    rects.append(fitz.Rect(span["bbox"]))
                for area in areas:
                    if isinstance(area, dict):
                        area_page = area.get("page")
                        if area_page is not None and int(area_page) != number + 1:
                            continue
                        rects.append(fitz.Rect(float(area["x0"]), float(area["y0"]), float(area["x1"]), float(area["y1"])))
                    elif len(area) == 4:
                        rects.append(fitz.Rect(*map(float, area)))
                for rect in rects:
                    page.add_redact_annot(rect, fill=(0, 0, 0))
                if rects:
                    # apply_redactions permanently removes covered text and images.
                    page.apply_redactions()
                reporter.report((number + 1) * 100 / len(doc), f"Redacted page {number + 1}")
            out = output_path(task, safe_stem(source), "redact", ".pdf")
            atomic_save(out, lambda temp: doc.save(temp, garbage=4, deflate=True))
            return [str(out)], {"pages": len(doc)}
        finally:
            doc.close()

    @action()
    def page_numbers(self, task, reporter):
        fitz = fitz_module()
        source = one_input(task)
        doc = fitz.open(source)
        try:
            position = str(task.options.get("position", "bottom-right")).lower()
            fmt = str(task.options.get("format", "{n}/{total}"))
            start = int(task.options.get("startAt", 1))
            size = float(task.options.get("fontSize", 10))
            for index, page in enumerate(doc):
                text = fmt.replace("{n}", str(start + index)).replace("{total}", str(len(doc)))
                margin = max(12, size)
                width = max(80, len(text) * size * 0.6 + 8)
                height = size * 1.5
                if "left" in position:
                    x0 = margin
                elif "center" in position:
                    x0 = (page.rect.width - width) / 2
                else:
                    x0 = page.rect.width - width - margin
                y0 = margin if "top" in position else page.rect.height - height - margin
                page.insert_textbox(fitz.Rect(x0, y0, x0 + width, y0 + height), text, fontsize=size, color=(0, 0, 0), overlay=True)
                reporter.report((index + 1) * 100 / len(doc), f"Numbered page {index + 1}")
            out = output_path(task, safe_stem(source), "page_numbers", ".pdf")
            atomic_save(out, lambda temp: doc.save(temp, garbage=4, deflate=True))
            return [str(out)], {}
        finally:
            doc.close()

    @action()
    def watermark(self, task, reporter):
        fitz = fitz_module()
        source = one_input(task)
        doc = fitz.open(source)
        try:
            text = task.options.get("text")
            image_path = task.options.get("imagePath")
            if not text and not image_path:
                raise EngineError("INVALID_TASK", "watermark requires text or imagePath")
            opacity = float(task.options.get("opacity", 0.25))
            rotation = float(task.options.get("rotation", 0)) % 360
            size = float(task.options.get("fontSize", 36))
            tile = bool(task.options.get("tile", False))
            # insert_image only supports right angles; text supports any angle via a morph matrix.
            image_rotation = int(round(rotation / 90.0)) * 90 % 360
            text_width = fitz.get_text_length(str(text), fontname="helv", fontsize=size) if text else 0
            for number, page in enumerate(doc):
                rects = []
                if tile:
                    for y in range(0, int(page.rect.height), int(size * 3)):
                        for x in range(0, int(page.rect.width), int(size * 6)):
                            rects.append(fitz.Rect(x, y, min(x + size * 6, page.rect.width), min(y + size * 2, page.rect.height)))
                else:
                    rects = [fitz.Rect(page.rect.width * .15, page.rect.height * .4, page.rect.width * .85, page.rect.height * .6)]
                for rect in rects:
                    if image_path:
                        page.insert_image(rect, filename=str(image_path), overlay=True, keep_proportion=True, rotate=image_rotation)
                    else:
                        center = fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
                        origin = fitz.Point(center.x - text_width / 2, center.y + size / 3)
                        page.insert_text(origin, str(text), fontsize=size, fontname="helv", color=(0.45, 0.45, 0.45),
                                         fill_opacity=opacity, overlay=True, morph=(center, fitz.Matrix(-rotation)))
                reporter.report((number + 1) * 100 / len(doc), f"Watermarked page {number + 1}")
            out = output_path(task, safe_stem(source), "watermark", ".pdf")
            atomic_save(out, lambda temp: doc.save(temp, garbage=4, deflate=True))
            return [str(out)], {"opacity": opacity}
        finally:
            doc.close()

    @action()
    def flatten(self, task, reporter):
        fitz = fitz_module()
        source = one_input(task)
        original = fitz.open(source)
        flattened = fitz.open()
        try:
            for number, page in enumerate(original):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False, annots=True)
                new_page = flattened.new_page(width=page.rect.width, height=page.rect.height)
                new_page.insert_image(new_page.rect, pixmap=pix)
                reporter.report((number + 1) * 100 / len(original), f"Flattened page {number + 1}")
            out = output_path(task, safe_stem(source), "flatten", ".pdf")
            atomic_save(out, lambda temp: flattened.save(temp, garbage=4, deflate=True))
            return [str(out)], {"pages": len(original)}
        finally:
            original.close()
            flattened.close()

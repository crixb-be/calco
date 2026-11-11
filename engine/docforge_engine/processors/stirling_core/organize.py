from __future__ import annotations

from pathlib import Path

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.pages import page_ranges
from ...util.paths import atomic_save, output_path, require_inputs, safe_stem
from .common import fitz_module, one_input


class PdfOrganizeProcessor(BaseProcessor):
    engine_name = "stirling_core"

    @action("merge_pdf")
    def merge_pdf(self, task, reporter):
        """Explicit Stirling-PDF Core name; keep ``merge`` for existing clients."""
        return self.merge(task, reporter)

    @action()
    def merge(self, task, reporter):
        fitz = fitz_module()
        inputs = require_inputs(task)
        order = task.options.get("order")
        if order is not None:
            indexes = [int(i) for i in order]
            if indexes and min(indexes) >= 1 and max(indexes) <= len(inputs):
                indexes = [i - 1 for i in indexes]
            try:
                inputs = [inputs[i] for i in indexes]
            except IndexError as exc:
                raise EngineError("INVALID_TASK", "merge.order contains an invalid file index") from exc
        out = output_path(task, safe_stem(inputs[0]), "merge", ".pdf")
        result = fitz.open()
        try:
            for number, path in enumerate(inputs):
                reporter.check_cancelled()
                source = fitz.open(path)
                try:
                    result.insert_pdf(source)
                finally:
                    source.close()
                reporter.report((number + 1) * 100 / len(inputs), f"Merged {path.name}")
            atomic_save(out, lambda temp: result.save(temp, garbage=4, deflate=True))
        finally:
            result.close()
        return [str(out)], {"pages": len(fitz.open(out))}

    @action()
    def split(self, task, reporter):
        fitz = fitz_module()
        source_path = one_input(task)
        source = fitz.open(source_path)
        try:
            mode = task.options.get("mode", "ranges")
            if mode == "every":
                size = int(task.options.get("every", task.options.get("n", 1)))
                if size < 1:
                    raise EngineError("INVALID_TASK", "split.every must be positive")
                groups = [list(range(i, min(i + size, len(source)))) for i in range(0, len(source), size)]
            elif mode == "single":
                groups = [[i] for i in page_ranges(task.options.get("pages", task.options.get("page", 1)), len(source))]
            else:
                ranges = task.options.get("ranges", "1-")
                groups = [page_ranges(item, len(source)) for item in str(ranges).split(";") if item.strip()]
            outputs = []
            for index, pages in enumerate(groups):
                reporter.check_cancelled()
                doc = fitz.open()
                try:
                    doc.insert_pdf(source, from_page=min(pages), to_page=max(pages), annots=True)
                    # Preserve non-contiguous range groups exactly.
                    if pages != list(range(min(pages), max(pages) + 1)):
                        doc.close()
                        doc = fitz.open()
                        for page_no in pages:
                            doc.insert_pdf(source, from_page=page_no, to_page=page_no, annots=True)
                    out = output_path(task, safe_stem(source_path), "split", ".pdf", index)
                    atomic_save(out, lambda temp, d=doc: d.save(temp, garbage=4, deflate=True))
                    outputs.append(str(out))
                finally:
                    doc.close()
                reporter.report((index + 1) * 100 / max(1, len(groups)), f"Wrote part {index + 1}")
            return outputs, {"parts": len(outputs)}
        finally:
            source.close()

    @action("split_pdf")
    def split_pdf(self, task, reporter):
        """Explicit Stirling-PDF Core name; keep ``split`` for existing clients."""
        return self.split(task, reporter)

    @action()
    def rotate(self, task, reporter):
        fitz = fitz_module()
        source_path = one_input(task)
        doc = fitz.open(source_path)
        try:
            angle = int(task.options.get("angle", 90))
            if angle not in (90, 180, 270):
                raise EngineError("INVALID_TASK", "rotate.angle must be 90, 180, or 270")
            pages = set(page_ranges(task.options.get("pages"), len(doc)))
            for number, page in enumerate(doc):
                if number in pages:
                    page.set_rotation((page.rotation + angle) % 360)
                reporter.report((number + 1) * 100 / len(doc), f"Rotated page {number + 1}")
            out = output_path(task, safe_stem(source_path), "rotate", ".pdf")
            atomic_save(out, lambda temp: doc.save(temp, garbage=4, deflate=True))
            return [str(out)], {"angle": angle}
        finally:
            doc.close()

    @action()
    def delete_pages(self, task, reporter):
        fitz = fitz_module()
        source_path = one_input(task)
        doc = fitz.open(source_path)
        try:
            indexes = page_ranges(task.options.get("pages"), len(doc))
            if len(indexes) == len(doc):
                raise EngineError("INVALID_TASK", "delete_pages cannot remove every page")
            for index in sorted(indexes, reverse=True):
                doc.delete_page(index)
            out = output_path(task, safe_stem(source_path), "delete_pages", ".pdf")
            atomic_save(out, lambda temp: doc.save(temp, garbage=4, deflate=True))
            reporter.report(100, "Deleted selected pages")
            return [str(out)], {"deleted": len(indexes)}
        finally:
            doc.close()

    @action()
    def crop(self, task, reporter):
        fitz = fitz_module()
        source_path = one_input(task)
        doc = fitz.open(source_path)
        try:
            box = _parse_box(task.options.get("box"))
            margins = _parse_margins(task.options.get("margins"))
            for number, page in enumerate(doc):
                rect = page.rect
                if box:
                    crop_box = fitz.Rect(*box)
                elif margins:
                    crop_box = fitz.Rect(rect.x0 + margins["left"], rect.y0 + margins["top"], rect.x1 - margins["right"], rect.y1 - margins["bottom"])
                else:
                    raise EngineError("INVALID_TASK", "crop requires box or margins")
                if crop_box.width <= 0 or crop_box.height <= 0:
                    raise EngineError("INVALID_TASK", "crop box is empty")
                page.set_cropbox(crop_box)
                reporter.report((number + 1) * 100 / len(doc), f"Cropped page {number + 1}")
            out = output_path(task, safe_stem(source_path), "crop", ".pdf")
            atomic_save(out, lambda temp: doc.save(temp, garbage=4, deflate=True))
            return [str(out)], {}
        finally:
            doc.close()

    @action()
    def nup(self, task, reporter):
        fitz = fitz_module()
        source_path = one_input(task)
        source = fitz.open(source_path)
        try:
            per_sheet = int(task.options.get("perSheet", 2))
            layouts = {2: (1, 2), 4: (2, 2), 6: (2, 3), 9: (3, 3)}
            if per_sheet not in layouts:
                raise EngineError("INVALID_TASK", "nup.perSheet must be 2, 4, 6, or 9")
            cols, rows = layouts[per_sheet]
            page_size = str(task.options.get("pageSize", "A4")).upper()
            width, height = ((612, 792) if page_size == "LETTER" else (595.28, 841.89))
            if task.options.get("landscape"):
                width, height = height, width
            out_doc = fitz.open()
            for start in range(0, len(source), per_sheet):
                out_page = out_doc.new_page(width=width, height=height)
                for offset in range(per_sheet):
                    page_no = start + offset
                    if page_no >= len(source):
                        break
                    col, row = offset % cols, offset // cols
                    rect = fitz.Rect(col * width / cols, row * height / rows, (col + 1) * width / cols, (row + 1) * height / rows)
                    out_page.show_pdf_page(rect, source, page_no)
                reporter.report(min(100, (min(start + per_sheet, len(source)) / len(source)) * 100), f"Composed sheet {start // per_sheet + 1}")
            out = output_path(task, safe_stem(source_path), "nup", ".pdf")
            atomic_save(out, lambda temp: out_doc.save(temp, garbage=4, deflate=True))
            out_doc.close()
            return [str(out)], {"sheets": (len(source) + per_sheet - 1) // per_sheet}
        finally:
            source.close()


def _numbers(value) -> list[float]:
    """Accept '1,2,3', '1 2 3', [1, 2, 3] or a single number."""
    if value is None or value == "":
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, str):
        return [float(part) for part in value.replace(";", ",").replace(" ", ",").split(",") if part.strip()]
    return [float(part) for part in value]


def _parse_box(value):
    """Crop box as dict {x0,y0,x1,y1}, list or 'x0,y0,x1,y1' string (points)."""
    if not value:
        return None
    if isinstance(value, dict):
        return [float(value[key]) for key in ("x0", "y0", "x1", "y1")]
    numbers = _numbers(value)
    if len(numbers) != 4:
        raise EngineError("INVALID_TASK", "box must have 4 values: x0,y0,x1,y1")
    return numbers


def _parse_margins(value):
    """Margins as dict {left,top,right,bottom}, a single number, or CSS-like 'top,right,bottom,left'."""
    if not value and value != 0:
        return None
    if isinstance(value, dict):
        return {side: float(value.get(side, 0)) for side in ("left", "top", "right", "bottom")}
    numbers = _numbers(value)
    if len(numbers) == 1:
        numbers *= 4
    elif len(numbers) == 2:
        numbers = numbers * 2
    if len(numbers) != 4:
        raise EngineError("INVALID_TASK", "margins must have 1, 2 or 4 values")
    top, right, bottom, left = numbers
    return {"left": left, "top": top, "right": right, "bottom": bottom}

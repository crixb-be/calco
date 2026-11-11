from __future__ import annotations

import math
import re
from pathlib import Path

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.pages import page_ranges
from ...util.paths import atomic_save, output_path, safe_stem
from .common import fitz_module, one_input, open_pdf


PRESETS = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "phone": r"(?<!\d)(?:\+?\d[\d ()-]{6,}\d)(?!\d)",
    "dni": r"(?<!\d)\d{8}(?!\d)",
    "iban": r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b",
    "card": r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)",
}


def _annotation_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EngineError("INVALID_TASK", f"{name} debe ser un número finito")
    return float(value)


def _annotation_color(value, name: str = "color") -> tuple[float, float, float]:
    if not isinstance(value, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        raise EngineError("INVALID_TASK", f"{name} debe tener formato #rrggbb")
    return tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))


class PdfEditProcessor(BaseProcessor):
    engine_name = "stirling_core"

    @action()
    def apply_annotations(self, task, reporter):
        fitz = fitz_module()
        source = one_input(task)
        annotations = task.options.get("annotations", [])
        if not isinstance(annotations, list):
            raise EngineError("INVALID_TASK", "annotations debe ser una lista")
        if len(annotations) > 5000:
            raise EngineError("INVALID_TASK", "No se permiten más de 5000 anotaciones")
        doc = open_pdf(fitz, source)
        try:
            per_page: dict[int, list[dict]] = {index: [] for index in range(len(doc))}
            for index, annotation in enumerate(annotations):
                if not isinstance(annotation, dict):
                    raise EngineError("INVALID_TASK", f"Anotación {index + 1} inválida")
                page_number = annotation.get("page")
                if isinstance(page_number, bool) or not isinstance(page_number, int) or not 0 <= page_number < len(doc):
                    raise EngineError("INVALID_TASK", f"Página inválida en la anotación {index + 1}")
                kind = annotation.get("kind")
                if kind == "text":
                    if not isinstance(annotation.get("text"), str):
                        raise EngineError("INVALID_TASK", f"Texto inválido en la anotación {index + 1}")
                    item = {
                        "kind": kind,
                        "x": _annotation_number(annotation.get("x"), "x"),
                        "y": _annotation_number(annotation.get("y"), "y"),
                        "size": _annotation_number(annotation.get("size"), "size"),
                        "color": _annotation_color(annotation.get("color")),
                        "text": annotation["text"],
                        "font": annotation.get("font", "helv"),
                        "bold": annotation.get("bold", False),
                    }
                    if item["font"] not in {"helv", "tiro", "cour"} or not isinstance(item["bold"], bool):
                        raise EngineError("INVALID_TASK", "font o bold inválido")
                    if item["size"] <= 0:
                        raise EngineError("INVALID_TASK", "size debe ser mayor que cero")
                elif kind == "ink":
                    raw_points = annotation.get("points")
                    if not isinstance(raw_points, list) or len(raw_points) < 2:
                        raise EngineError("INVALID_TASK", f"Trazo inválido en la anotación {index + 1}")
                    points = []
                    for point in raw_points:
                        if not isinstance(point, (list, tuple)) or len(point) != 2:
                            raise EngineError("INVALID_TASK", f"Punto inválido en la anotación {index + 1}")
                        points.append((_annotation_number(point[0], "x"), _annotation_number(point[1], "y")))
                    width = _annotation_number(annotation.get("width"), "width")
                    if width <= 0:
                        raise EngineError("INVALID_TASK", "width debe ser mayor que cero")
                    item = {"kind": kind, "points": points, "width": width, "color": _annotation_color(annotation.get("color"))}
                elif kind == "highlight":
                    width = _annotation_number(annotation.get("w"), "w")
                    height = _annotation_number(annotation.get("h"), "h")
                    if width < 0 or height < 0:
                        raise EngineError("INVALID_TASK", "El resaltado debe tener tamaño positivo")
                    item = {
                        "kind": kind,
                        "x": _annotation_number(annotation.get("x"), "x"),
                        "y": _annotation_number(annotation.get("y"), "y"),
                        "w": width,
                        "h": height,
                        "color": _annotation_color(annotation.get("color")),
                    }
                elif kind == "rect":
                    width = _annotation_number(annotation.get("w"), "w")
                    height = _annotation_number(annotation.get("h"), "h")
                    stroke_width = _annotation_number(annotation.get("width"), "width")
                    if width < 0 or height < 0 or stroke_width <= 0:
                        raise EngineError("INVALID_TASK", "Rectángulo inválido")
                    item = {"kind": kind, "x": _annotation_number(annotation.get("x"), "x"), "y": _annotation_number(annotation.get("y"), "y"), "w": width, "h": height, "width": stroke_width, "color": _annotation_color(annotation.get("color"))}
                elif kind == "line":
                    stroke_width = _annotation_number(annotation.get("width"), "width")
                    if stroke_width <= 0:
                        raise EngineError("INVALID_TASK", "width debe ser mayor que cero")
                    item = {"kind": kind, "x1": _annotation_number(annotation.get("x1"), "x1"), "y1": _annotation_number(annotation.get("y1"), "y1"), "x2": _annotation_number(annotation.get("x2"), "x2"), "y2": _annotation_number(annotation.get("y2"), "y2"), "width": stroke_width, "color": _annotation_color(annotation.get("color"))}
                elif kind == "image":
                    raw_path = annotation.get("path")
                    if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
                        raise EngineError("INVALID_TASK", "La ruta de imagen debe ser absoluta")
                    image_path = Path(raw_path)
                    if not image_path.is_file() or image_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                        raise EngineError("INVALID_TASK", "Imagen no encontrada o extensión inválida")
                    if image_path.stat().st_size > 20 * 1024 * 1024:
                        raise EngineError("INVALID_TASK", "La imagen supera el límite de 20 MB")
                    width = _annotation_number(annotation.get("w"), "w")
                    height = _annotation_number(annotation.get("h"), "h")
                    if width <= 0 or height <= 0:
                        raise EngineError("INVALID_TASK", "La imagen debe tener tamaño positivo")
                    item = {"kind": kind, "x": _annotation_number(annotation.get("x"), "x"), "y": _annotation_number(annotation.get("y"), "y"), "w": width, "h": height, "path": str(image_path)}
                else:
                    raise EngineError("INVALID_TASK", f"Tipo de anotación no soportado: {kind}")
                per_page[page_number].append(item)

            def display_point(page, x: float, y: float):
                # The UI stores PDF.js viewport coordinates (top-left, rotated page space).
                # PyMuPDF's derotation matrix maps them back to the page's PDF coordinates.
                return fitz.Point(x, y) * page.derotation_matrix

            def display_rect(page, annotation):
                corners = [
                    display_point(page, annotation["x"], annotation["y"]),
                    display_point(page, annotation["x"] + annotation["w"], annotation["y"]),
                    display_point(page, annotation["x"] + annotation["w"], annotation["y"] + annotation["h"]),
                    display_point(page, annotation["x"], annotation["y"] + annotation["h"]),
                ]
                return fitz.Rect(min(point.x for point in corners), min(point.y for point in corners), max(point.x for point in corners), max(point.y for point in corners))

            for number, page in enumerate(doc):
                reporter.check_cancelled()
                for annotation in per_page[number]:
                    color = annotation.get("color")
                    if annotation["kind"] == "text":
                        size = annotation["size"]
                        for line_number, line in enumerate(annotation["text"].split("\n")):
                            # The UI positions a div at y with CSS line-height 1.2; PyMuPDF needs its baseline.
                            point = display_point(page, annotation["x"], annotation["y"] + size * (line_number * 1.2 + 0.8))
                            font = {"helv": "hebo", "tiro": "tibo", "cour": "cobo"}[annotation["font"]] if annotation["bold"] else annotation["font"]
                            page.insert_text(point, line, fontsize=size, color=color, fontname=font, overlay=True)
                    elif annotation["kind"] == "ink":
                        points = [display_point(page, x, y) for x, y in annotation["points"]]
                        page.draw_polyline(points, color=color, width=annotation["width"], lineCap=1, lineJoin=1, closePath=False, overlay=True)
                    elif annotation["kind"] == "highlight":
                        page.draw_rect(display_rect(page, annotation), color=None, fill=color, fill_opacity=0.35, overlay=True)
                    elif annotation["kind"] == "rect":
                        page.draw_rect(display_rect(page, annotation), color=color, width=annotation["width"], overlay=True)
                    elif annotation["kind"] == "line":
                        start = display_point(page, annotation["x1"], annotation["y1"])
                        end = display_point(page, annotation["x2"], annotation["y2"])
                        page.draw_line(start, end, color=color, width=annotation["width"], lineCap=1, overlay=True)
                    elif annotation["kind"] == "image":
                        page.insert_image(display_rect(page, annotation), filename=annotation["path"], keep_proportion=False, overlay=True, rotate=int(page.rotation) % 360)
                reporter.report((number + 1) * 100 / len(doc), f"Editada página {number + 1}")
            out = output_path(task, safe_stem(source), "editado", ".pdf")
            atomic_save(out, lambda temp: doc.save(temp, garbage=3, deflate=True))
            return [str(out)], {"pages": len(doc), "annotations": len(annotations)}
        finally:
            doc.close()

    @action()
    def redact(self, task, reporter):
        fitz = fitz_module()
        source = one_input(task)
        doc = open_pdf(fitz, source)
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
        doc = open_pdf(fitz, source)
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
        doc = open_pdf(fitz, source)
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
        original = open_pdf(fitz, source)
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

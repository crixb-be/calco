"""stirling_core.apply_page_plan — visual page operations from the page grid (ARCHITECTURE.md §6.3).

options:
  sequence:   [{sourceIndex, pageIndex, rotation?}]  canonical form, final order, multi-file
  plans:      [{sourcePath, pageOrder, rotations, deletedPages}]  alternative form, concatenated
  outputMode: "single" (default) | "per_page" | "per_source"
  outputName: optional file name for "single"
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.paths import atomic_save, output_path, require_inputs, safe_stem
from .common import fitz_module

OUTPUT_MODES = {"single", "per_page", "per_source"}


@dataclass(frozen=True)
class PageRef:
    source_index: int
    page_index: int
    rotation: int = 0  # extra clockwise rotation, normalised to 0/90/180/270


def normalize_rotation(value: Any) -> int:
    try:
        degrees = int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise EngineError("INVALID_TASK", f"Rotación inválida: {value!r}") from exc
    if degrees % 90:
        raise EngineError("INVALID_TASK", f"La rotación debe ser múltiplo de 90: {degrees}")
    return degrees % 360


def _int(value: Any, what: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise EngineError("INVALID_TASK", f"{what} debe ser un entero: {value!r}") from exc


def _same_path(a: str | Path, b: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def build_sequence(options: dict[str, Any], inputs: list[Path]) -> list[PageRef]:
    if options.get("sequence") is not None:
        raw = options["sequence"]
        if not isinstance(raw, list):
            raise EngineError("INVALID_TASK", "sequence debe ser una lista")
        refs = []
        for item in raw:
            if not isinstance(item, dict):
                raise EngineError("INVALID_TASK", "Cada elemento de sequence debe ser un objeto")
            refs.append(PageRef(
                _int(item.get("sourceIndex", 0), "sourceIndex"),
                _int(item.get("pageIndex"), "pageIndex"),
                normalize_rotation(item.get("rotation", 0)),
            ))
        return refs

    plans = options.get("plans")
    if plans is None:
        raise EngineError("INVALID_TASK", "apply_page_plan requiere 'sequence' o 'plans'")
    if isinstance(plans, dict):
        plans = [plans]
    refs = []
    for plan in plans:
        source_path = plan.get("sourcePath")
        matches = [i for i, p in enumerate(inputs) if source_path and _same_path(p, source_path)]
        if not matches:
            raise EngineError("INVALID_TASK", f"sourcePath no está en inputFiles: {source_path}")
        source_index = matches[0]
        rotations = {_int(k, "rotations key"): normalize_rotation(v) for k, v in (plan.get("rotations") or {}).items()}
        deleted = {_int(i, "deletedPages") for i in (plan.get("deletedPages") or [])}
        order = plan.get("pageOrder")
        if order is None:
            order = range(_page_count(inputs[source_index]))
        for page_index in order:
            page_index = _int(page_index, "pageOrder")
            if page_index in deleted:
                continue
            refs.append(PageRef(source_index, page_index, rotations.get(page_index, 0)))
    return refs


def _page_count(path: Path) -> int:
    fitz = fitz_module()
    with fitz.open(path) as doc:
        return doc.page_count


class PdfPagePlanProcessor(BaseProcessor):
    engine_name = "stirling_core"

    @action()
    def apply_page_plan(self, task, reporter):
        fitz = fitz_module()
        inputs = require_inputs(task)
        mode = str(task.options.get("outputMode", "single"))
        if mode not in OUTPUT_MODES:
            raise EngineError("INVALID_TASK", f"outputMode inválido: {mode}")
        sequence = build_sequence(task.options, inputs)
        if not sequence:
            raise EngineError("INVALID_TASK", "El plan no contiene páginas (¿todas marcadas para eliminar?)")

        sources = {}
        try:
            # Validate every reference before writing anything.
            for ref in sequence:
                if ref.source_index < 0 or ref.source_index >= len(inputs):
                    raise EngineError("INVALID_TASK", f"sourceIndex fuera de rango: {ref.source_index}")
                if ref.source_index not in sources:
                    doc = fitz.open(inputs[ref.source_index])
                    if doc.needs_pass:
                        doc.close()
                        raise EngineError("WRONG_PASSWORD", f"PDF protegido: {inputs[ref.source_index].name}")
                    sources[ref.source_index] = doc
                count = sources[ref.source_index].page_count
                if ref.page_index < 0 or ref.page_index >= count:
                    raise EngineError(
                        "INVALID_TASK",
                        f"pageIndex {ref.page_index} fuera de rango en {inputs[ref.source_index].name} ({count} páginas)",
                    )

            groups = self._group(sequence, mode)
            outputs = []
            done, total = 0, len(sequence)
            for group_no, (stem_source, refs) in enumerate(groups):
                result = fitz.open()
                try:
                    for ref in refs:
                        reporter.check_cancelled()
                        src = sources[ref.source_index]
                        result.insert_pdf(src, from_page=ref.page_index, to_page=ref.page_index, links=True, annots=True)
                        if ref.rotation:
                            page = result[-1]
                            page.set_rotation((page.rotation + ref.rotation) % 360)
                        done += 1
                        reporter.report(done * 100 / total, f"Página {done}/{total}")
                    index = None if len(groups) == 1 else group_no
                    out = output_path(task, safe_stem(inputs[stem_source]), "pages", ".pdf", index)
                    atomic_save(out, lambda temp, doc=result: doc.save(temp, garbage=3, deflate=True))
                    outputs.append(str(out))
                finally:
                    result.close()
            return outputs, {"pages": total, "files": len(outputs), "outputMode": mode}
        finally:
            for doc in sources.values():
                doc.close()

    @staticmethod
    def _group(sequence: list[PageRef], mode: str) -> list[tuple[int, list[PageRef]]]:
        if mode == "per_page":
            return [(ref.source_index, [ref]) for ref in sequence]
        if mode == "per_source":
            groups: dict[int, list[PageRef]] = {}
            for ref in sequence:
                groups.setdefault(ref.source_index, []).append(ref)
            return list(groups.items())
        return [(sequence[0].source_index, sequence)]

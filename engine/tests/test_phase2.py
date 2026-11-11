"""Phase 2: RPC channel, thumbnail cache and apply_page_plan."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import fitz
import pytest

from docforge_engine import rpc
from docforge_engine.contract import ProcessorTask
from docforge_engine.errors import EngineError
from docforge_engine.registry import EngineRegistry
from docforge_engine.util.thumbnail_generator import ThumbnailService


def make_pdf(path: Path, pages: int, label: str = "P", landscape_every: int = 0) -> Path:
    doc = fitz.open()
    for i in range(pages):
        landscape = landscape_every and (i + 1) % landscape_every == 0
        page = doc.new_page(width=842 if landscape else 595, height=595 if landscape else 842)
        page.insert_text((72, 100), f"{label}{i + 1}", fontsize=28)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()
    return path


def page_labels(path: str | Path) -> list[str]:
    with fitz.open(path) as doc:
        return [page.get_text().strip() for page in doc]


def run_plan(inputs, out_dir, **options):
    task = ProcessorTask(id="plan", engine="stirling_core", action="apply_page_plan",
                         inputFiles=[str(p) for p in inputs], outputDir=str(out_dir), options=options)
    outputs, meta = EngineRegistry().execute(task, lambda e: None, threading.Event())
    return [Path(p) for p in outputs], meta


@pytest.fixture()
def service(tmp_path):
    return ThumbnailService(cache_root=tmp_path / "thumbs")


# ---------------------------------------------------------------- thumbnails & metadata

def test_metadata_is_fast_for_large_pdf(tmp_path, service):
    pdf = make_pdf(tmp_path / "big.pdf", 120, landscape_every=10)
    started = time.perf_counter()
    meta = service.metadata(str(pdf))
    elapsed = time.perf_counter() - started
    assert meta["pageCount"] == 120 and len(meta["pages"]) == 120
    assert meta["pages"][9]["width"] > meta["pages"][9]["height"]  # landscape page reported correctly
    assert len(meta["fileHash"]) == 40
    assert elapsed < 2.0
    assert not (tmp_path / "thumbs").exists()  # metadata never renders


def test_thumbnail_batch_and_disk_cache(tmp_path):
    pdf = make_pdf(tmp_path / "doc.pdf", 30)
    first = ThumbnailService(cache_root=tmp_path / "thumbs")
    batch = first.thumbnails(str(pdf), start=24, count=12, max_width=200)
    assert [b["index"] for b in batch] == list(range(24, 30))  # clipped at the last page
    header, data = batch[0]["url"].split(",", 1)
    assert header in ("data:image/webp;base64", "data:image/png;base64")
    assert base64.b64decode(data)[:4] in (b"RIFF", b"\x89PNG")
    assert batch[0]["width"] <= 200
    cached = list((tmp_path / "thumbs").rglob("*.webp")) + list((tmp_path / "thumbs").rglob("*.png"))
    assert len(cached) == 6

    # A fresh service (empty memory cache) must serve from disk without rendering.
    second = ThumbnailService(cache_root=tmp_path / "thumbs")
    second._render = lambda *a, **k: (_ for _ in ()).throw(AssertionError("rendered instead of disk cache"))
    again = second.thumbnails(str(pdf), start=24, count=6, max_width=200)
    assert [a["url"] for a in again] == [b["url"] for b in batch]


def test_thumbnail_limits_and_errors(tmp_path, service):
    pdf = make_pdf(tmp_path / "doc.pdf", 3)
    with pytest.raises(EngineError) as too_many:
        service.thumbnails(str(pdf), start=0, count=25)
    assert too_many.value.code == "INVALID_TASK"
    with pytest.raises(EngineError) as out_of_range:
        service.image(str(pdf), 7)
    assert out_of_range.value.code == "INVALID_TASK"
    protected = tmp_path / "locked.pdf"
    with fitz.open(pdf) as doc:
        doc.save(protected, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secreto", owner_pw="dueno")
    with pytest.raises(EngineError) as locked:
        service.metadata(str(protected))
    assert locked.value.code == "WRONG_PASSWORD"
    assert service.metadata(str(protected), password="secreto")["pageCount"] == 3


def test_cleanup_removes_old_cache(tmp_path):
    service = ThumbnailService(cache_root=tmp_path / "thumbs")
    old = tmp_path / "thumbs" / "oldhash"
    old.mkdir(parents=True)
    past = time.time() - 8 * 24 * 3600
    os.utime(old, (past, past))
    (tmp_path / "thumbs" / "fresh").mkdir()
    assert service.cleanup() == 1
    assert not old.exists() and (tmp_path / "thumbs" / "fresh").exists()


# ---------------------------------------------------------------- rpc methods

def test_rpc_methods(tmp_path):
    pdf = make_pdf(tmp_path / "MAESTRÍA" / "doc.pdf", 4)
    meta = rpc.dispatch("get_pdf_pages_metadata", {"pdfPath": str(pdf)})
    assert meta["pageCount"] == 4
    thumbs = rpc.dispatch("get_page_thumbnails", {"pdfPath": str(pdf), "start": 0, "count": 2, "maxWidth": 120})
    assert [p["index"] for p in thumbs["pages"]] == [0, 1] and thumbs["pages"][0]["thumbUrl"].startswith("data:image/")
    page = rpc.dispatch("render_page", {"pdfPath": str(pdf), "index": 3, "maxWidth": 800})
    assert page["index"] == 3 and page["width"] <= 800 and page["imageUrl"].startswith("data:image/")

    md = tmp_path / "Gestión.md"
    md.write_text("# Título\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")
    read = rpc.dispatch("read_text_file", {"path": str(md)})
    assert read["content"].startswith("# Título") and read["size"] == md.stat().st_size
    with pytest.raises(EngineError) as denied:
        rpc.dispatch("read_text_file", {"path": str(pdf)})
    assert denied.value.code == "INVALID_TASK"
    with pytest.raises(EngineError) as too_big:
        rpc.dispatch("read_text_file", {"path": str(md), "maxBytes": 5})
    assert too_big.value.code == "INVALID_TASK"

    target = tmp_path / "Exportado Ñ" / "resultado.md"
    exported = rpc.dispatch("export_file", {"sourcePath": str(md), "targetPath": str(target)})
    assert Path(exported["path"]) == target and target.read_text(encoding="utf-8") == md.read_text(encoding="utf-8")

    with pytest.raises(EngineError) as unknown:
        rpc.dispatch("nope", {})
    assert unknown.value.code == "UNKNOWN_ACTION"
    with pytest.raises(EngineError) as relative:
        rpc.dispatch("get_pdf_pages_metadata", {"pdfPath": "doc.pdf"})
    assert relative.value.code == "INVALID_TASK"


def test_rpc_over_serve_with_accented_path(tmp_path):
    pdf = make_pdf(tmp_path / "MAESTRÍA GESTIÓN" / "Tesis Maestría.pdf", 5)
    messages = [
        {"type": "rpc", "rpcId": "r1", "method": "get_pdf_pages_metadata", "params": {"pdfPath": str(pdf)}},
        {"type": "rpc", "rpcId": "r2", "method": "get_page_thumbnails", "params": {"pdfPath": str(pdf), "start": 0, "count": 3}},
        {"type": "rpc", "rpcId": "r3", "method": "does_not_exist", "params": {}},
    ]
    payload = "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages).encode("utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    proc = subprocess.run([sys.executable, "-m", "docforge_engine", "serve"], input=payload,
                          capture_output=True, timeout=60, env=env)
    results = {e["rpcId"]: e for e in (json.loads(l.decode("utf-8")) for l in proc.stdout.splitlines() if l.strip())
               if e.get("type") == "rpc_result"}
    assert results["r1"]["ok"] and results["r1"]["result"]["pageCount"] == 5
    assert results["r2"]["ok"] and len(results["r2"]["result"]["pages"]) == 3
    assert not results["r3"]["ok"] and results["r3"]["error"]["code"] == "UNKNOWN_ACTION"


# ---------------------------------------------------------------- apply_page_plan

def test_plan_sequence_reorder_rotate_delete(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", 5, "A")
    # Final order 5,1,3 (pages 2 and 4 deleted), with rotations incl. a negative one.
    seq = [{"sourceIndex": 0, "pageIndex": 4, "rotation": 90},
           {"sourceIndex": 0, "pageIndex": 0, "rotation": -90},
           {"sourceIndex": 0, "pageIndex": 2}]
    (out,), meta = run_plan([pdf], tmp_path / "out", sequence=seq)
    assert page_labels(out) == ["A5", "A1", "A3"]
    with fitz.open(out) as doc:
        assert [p.rotation for p in doc] == [90, 270, 0]
    assert meta["pages"] == 3 and out.name == "a_pages.pdf"


def test_plan_adds_to_existing_rotation(tmp_path):
    pdf = make_pdf(tmp_path / "r.pdf", 1)
    with fitz.open(pdf) as doc:
        doc[0].set_rotation(90)
        doc.saveIncr()
    (out,), _ = run_plan([pdf], tmp_path / "out", sequence=[{"sourceIndex": 0, "pageIndex": 0, "rotation": 270}])
    with fitz.open(out) as doc:
        assert doc[0].rotation == 0


def test_plan_plans_form(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", 4, "A")
    plan = {"sourcePath": str(pdf), "pageOrder": [3, 2, 1, 0], "rotations": {"2": 180}, "deletedPages": [1]}
    (out,), _ = run_plan([pdf], tmp_path / "out", plans=[plan])
    assert page_labels(out) == ["A4", "A3", "A1"]
    with fitz.open(out) as doc:
        assert [p.rotation for p in doc] == [0, 180, 0]


def test_plan_multi_source_interleave_and_modes(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", 2, "A")
    b = make_pdf(tmp_path / "b.pdf", 2, "B")
    seq = [{"sourceIndex": 0, "pageIndex": 0}, {"sourceIndex": 1, "pageIndex": 0},
           {"sourceIndex": 0, "pageIndex": 1}, {"sourceIndex": 1, "pageIndex": 1}]
    (merged,), _ = run_plan([a, b], tmp_path / "out", sequence=seq, outputName="Unido Ñ.pdf")
    assert page_labels(merged) == ["A1", "B1", "A2", "B2"] and merged.name == "Unido Ñ.pdf"

    per_page, meta = run_plan([a, b], tmp_path / "pp", sequence=seq, outputMode="per_page")
    assert len(per_page) == 4 and meta["files"] == 4
    assert [page_labels(p) for p in per_page] == [["A1"], ["B1"], ["A2"], ["B2"]]

    per_source, _ = run_plan([a, b], tmp_path / "ps", sequence=seq, outputMode="per_source")
    assert [page_labels(p) for p in per_source] == [["A1", "A2"], ["B1", "B2"]]


@pytest.mark.parametrize("options, fragment", [
    ({"sequence": [{"sourceIndex": 0, "pageIndex": 9}]}, "pageIndex 9"),
    ({"sequence": [{"sourceIndex": 3, "pageIndex": 0}]}, "sourceIndex"),
    ({"sequence": [{"sourceIndex": 0, "pageIndex": 0, "rotation": 45}]}, "múltiplo de 90"),
    ({"sequence": []}, "no contiene páginas"),
    ({}, "requiere"),
    ({"sequence": [{"sourceIndex": 0, "pageIndex": 0}], "outputMode": "zip"}, "outputMode"),
    ({"plans": [{"sourcePath": "C:/otro.pdf", "pageOrder": [0]}]}, "sourcePath"),
])
def test_plan_validation_errors(tmp_path, options, fragment):
    pdf = make_pdf(tmp_path / "a.pdf", 2)
    with pytest.raises(EngineError) as error:
        run_plan([pdf], tmp_path / "out", **options)
    assert error.value.code == "INVALID_TASK" and fragment in error.value.message
    assert not list((tmp_path / "out").glob("*.pdf"))  # nothing written on validation failure


# ---------------------------------------------------------------- resolution tiers (legibility)

def test_tiers_enforce_min_dpi_for_reading_sizes(tmp_path, service):
    pdf = make_pdf(tmp_path / "doc.pdf", 2)  # A4: 595 pt wide
    small = service.image(str(pdf), 0, max_width=220, tier="M")
    assert small["dpi"] < 40 and small["width"] <= 220            # width-driven overview
    for tier in ("L", "XL", "modal"):
        sharp = service.image(str(pdf), 0, max_width=320, tier=tier)
        assert sharp["dpi"] >= 144, tier                           # >= zoom 2.0 regardless of card width
        assert sharp["width"] >= 1190                              # ~ 595pt * 2
    big_modal = service.image(str(pdf), 0, max_width=2400, tier="modal")
    assert big_modal["dpi"] == 216                                 # modal cap (zoom 3.0)
    assert service.image(str(pdf), 0, max_width=2400, tier="L")["dpi"] == 160  # L cap


def test_tier_cache_keys_are_separate(tmp_path, service):
    pdf = make_pdf(tmp_path / "doc.pdf", 1)
    a = service.image(str(pdf), 0, max_width=320, tier="M")
    b = service.image(str(pdf), 0, max_width=320, tier="L")
    assert a["url"] != b["url"]
    variants = sorted(p.name for p in next((tmp_path / "thumbs").iterdir()).iterdir())
    assert variants == [f"L_320_144", f"M_320_{a['dpi']}"]           # hash / tier_width_dpi / index


def test_tier_validation(tmp_path, service):
    pdf = make_pdf(tmp_path / "doc.pdf", 1)
    with pytest.raises(EngineError):
        service.image(str(pdf), 0, tier="XXL")
    with pytest.raises(EngineError):
        service.thumbnails(str(pdf), 0, 1, tier="modal")
    result = rpc.dispatch("get_page_thumbnails", {"pdfPath": str(pdf), "start": 0, "count": 1, "maxWidth": 440, "tier": "XL"})
    assert result["pages"][0]["dpi"] >= 144 and result["pages"][0]["tier"] == "XL"
    page = rpc.dispatch("render_page", {"pdfPath": str(pdf), "index": 0, "maxWidth": 1800, "tier": "modal"})
    assert page["dpi"] >= 144 and page["tier"] == "modal"

"""Regression: discrete page selections ("1,3", "3,5") must export only those pages and keep
the source PDF's page numbers in JSON and DocTags.

Docling converts the spanning range (3-5 for "3,5"); ``DoclingDocument.filter`` then rebases
page numbers (3,5 -> 1,3), which ``_shift_pages`` must undo. Documents are built by hand, so no
Docling models are loaded."""
from __future__ import annotations

import copy
import json

import pytest

pytest.importorskip("docling_core")

from docling_core.types.doc import BoundingBox, DocItemLabel, DoclingDocument, ProvenanceItem, Size  # noqa: E402

from docforge_engine.processors.docling_core.parse import (  # noqa: E402
    DoclingProcessor,
    _only_pages,
    _shift_pages,
    normalize_page_selection,
)

MARKERS = {n: f"MARCADOR_P{n}" for n in range(1, 6)}


def _document(page_numbers) -> DoclingDocument:
    doc = DoclingDocument(name="prueba")
    for n in page_numbers:
        doc.add_page(page_no=n, size=Size(width=612, height=792))
        text = MARKERS[n]
        doc.add_text(
            label=DocItemLabel.PARAGRAPH,
            text=text,
            prov=ProvenanceItem(page_no=n, bbox=BoundingBox(l=72, t=700, r=300, b=680), charspan=(0, len(text))),
        )
    return doc


@pytest.fixture
def full_doc() -> DoclingDocument:
    """Whole 5-page document (selection starting at page 1)."""
    return _document(range(1, 6))


@pytest.fixture
def tail_doc() -> DoclingDocument:
    """What Docling returns for page_range (3, 5): pages 3, 4 and 5 only."""
    return _document(range(3, 6))


def _json(doc, pages):
    content, ext = DoclingProcessor._export(doc, "json", pages)
    assert ext == ".json"
    return content, json.loads(content)


def _prov_pages(data) -> set[int]:
    return {prov["page_no"] for item in data["texts"] for prov in item.get("prov", [])}


def _assert_only(content: str, selected) -> None:
    for n, marker in MARKERS.items():
        assert (marker in content) == (n in selected), f"page {n} marker presence wrong for {selected}"


@pytest.mark.parametrize(
    ("fixture", "pages"),
    [("full_doc", [1, 3]), ("tail_doc", [3, 5])],
    ids=["1,3", "3,5"],
)
def test_json_keeps_only_selected_pages_with_original_numbers(request, fixture, pages):
    content, data = _json(request.getfixturevalue(fixture), pages)

    assert set(data["pages"]) == {str(n) for n in pages}
    for key, page in data["pages"].items():
        assert page["page_no"] == int(key)
    assert _prov_pages(data) == set(pages)
    _assert_only(content, pages)


@pytest.mark.parametrize(
    ("fixture", "pages"),
    [("full_doc", [1, 3]), ("tail_doc", [3, 5])],
    ids=["1,3", "3,5"],
)
def test_doctags_keeps_only_selected_pages(request, fixture, pages):
    content, ext = DoclingProcessor._export(request.getfixturevalue(fixture), "doctags", pages)
    assert ext == ".doctags"
    _assert_only(content, pages)


@pytest.mark.parametrize("pages", [None, [], [1, 2, 3, 4, 5]], ids=["none", "empty", "all"])
def test_no_or_full_selection_exports_everything(full_doc, pages):
    content, data = _json(full_doc, pages)
    assert set(data["pages"]) == {"1", "2", "3", "4", "5"}
    assert _prov_pages(data) == {1, 2, 3, 4, 5}
    _assert_only(content, range(1, 6))


def test_only_pages_returns_same_document_when_nothing_to_filter(full_doc):
    assert _only_pages(full_doc, None) is full_doc
    assert _only_pages(full_doc, []) is full_doc
    assert _only_pages(full_doc, [1, 2, 3, 4, 5]) is full_doc


def test_only_pages_filters_to_requested_pages(tail_doc):
    filtered = _only_pages(tail_doc, [3, 5])
    assert len(filtered.pages) == 2


def test_shift_pages_zero_offset_is_noop():
    data = {"pages": {"1": {"page_no": 1}}, "texts": [{"prov": [{"page_no": 1}]}]}
    before = copy.deepcopy(data)
    _shift_pages(data, 0)
    assert data == before


def test_shift_pages_moves_page_keys_and_nested_prov():
    data = {
        "pages": {"1": {"page_no": 1}, "3": {"page_no": 3}},
        "texts": [{"prov": [{"page_no": 1}, {"page_no": 3}]}],
        "tables": [{"children": [{"prov": [{"page_no": 3}]}], "prov": [{"page_no": 1}]}],
        "body": {"name": "_root_"},
    }
    _shift_pages(data, 2)
    assert data["pages"] == {"3": {"page_no": 3}, "5": {"page_no": 5}}
    assert [p["page_no"] for p in data["texts"][0]["prov"]] == [3, 5]
    assert data["tables"][0]["prov"][0]["page_no"] == 3
    assert data["tables"][0]["children"][0]["prov"][0]["page_no"] == 5
    assert data["body"] == {"name": "_root_"}


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        ("1,3", ((1, 3), [1, 3])),
        ("3,5", ((3, 5), [3, 5])),
        ("2-4", ((2, 4), None)),
        ("", (None, None)),
        (None, (None, None)),
        ("1-5", (None, None)),
    ],
)
def test_normalize_page_selection(pages, expected):
    assert normalize_page_selection(pages, 5) == expected


def test_export_does_not_mutate_source_document(full_doc):
    _json(full_doc, [1, 3])
    DoclingProcessor._export(full_doc, "doctags", [1, 3])
    assert sorted(full_doc.pages) == [1, 2, 3, 4, 5]
    assert {prov.page_no for item in full_doc.texts for prov in item.prov} == {1, 2, 3, 4, 5}

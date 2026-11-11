from __future__ import annotations

from pathlib import Path

import fitz
import pytest
from PIL import Image, ImageDraw


@pytest.fixture(autouse=True)
def _no_real_office_com(monkeypatch):
    """Never drive a real Word/Excel/PowerPoint from tests (also inherited by `serve` subprocesses).

    Cascade tests monkeypatch ``com_available`` explicitly, which overrides this.
    """
    monkeypatch.setenv("DOCFORGE_DISABLE_OFFICE_COM", "1")


@pytest.fixture()
def fixture_dir(tmp_path: Path):
    image_path = tmp_path / "fixture.png"
    image = Image.new("RGB", (160, 80), "white")
    ImageDraw.Draw(image).rectangle((10, 10, 150, 70), outline="black", width=3)
    image.save(image_path)
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    for number in range(3):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 90), f"Page {number + 1} - secret@example.com - 12345678", fontsize=16)
        if number == 0:
            page.insert_text((72, 140), "Name    Amount\nAlice   10\nBob     20", fontsize=12)
            page.insert_image(fitz.Rect(72, 180, 232, 260), filename=str(image_path))
    doc.save(pdf_path)
    doc.close()
    return {"dir": tmp_path, "pdf": pdf_path, "image": image_path}

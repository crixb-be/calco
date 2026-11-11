"""stirling_core.image_convert (Pillow transcoding) and WebP support in images_to_pdf."""
from __future__ import annotations

import threading
from pathlib import Path

import fitz
import pytest
from PIL import Image

from docforge_engine.contract import parse_task
from docforge_engine.errors import EngineError
from docforge_engine.registry import EngineRegistry


def run(action, inputs, output_dir, **options):
    events: list[dict] = []
    task = parse_task({
        "id": "img", "engine": "stirling_core", "action": action,
        "inputFiles": [str(p) for p in inputs], "outputDir": str(output_dir), "options": options,
    })
    outputs, meta = EngineRegistry().execute(task, events.append, threading.Event())
    return [Path(p) for p in outputs], meta, events


@pytest.fixture()
def accented_dir(tmp_path: Path) -> Path:
    path = tmp_path / "MAESTRÍA GESTIÓN" / "imágenes"
    path.mkdir(parents=True)
    return path


def _rgba_png(folder: Path, name="código.png") -> Path:
    image = Image.new("RGBA", (64, 48), (255, 0, 0, 0))  # fully transparent red
    image.paste((0, 0, 255, 255), (16, 12, 48, 36))  # opaque blue square
    path = folder / name
    image.save(path, dpi=(300, 300))
    return path


def test_png_with_alpha_to_jpg_flattens_on_white_and_keeps_dpi(accented_dir):
    source = _rgba_png(accented_dir)
    outputs, meta, events = run("image_convert", [source], accented_dir / "salida", format="jpg")

    assert len(outputs) == 1 and outputs[0].suffix == ".jpg" and outputs[0].is_file()
    assert "MAESTRÍA GESTIÓN" in str(outputs[0])
    with Image.open(outputs[0]) as out:
        assert out.format == "JPEG" and out.mode == "RGB"
        corner = out.getpixel((1, 1))
        assert all(channel > 245 for channel in corner), corner  # transparent -> white, not black
        centre = out.getpixel((32, 24))
        assert centre[2] > 200 and centre[0] < 60
        assert round(out.info["dpi"][0]) == 300
    assert meta == {"format": "jpg", "quality": 85, "count": 1}
    progress = [e for e in events if e["type"] == "progress"]
    assert progress[-1]["percent"] == 100
    assert any("fondo blanco" in e.get("message", "") for e in events if e["type"] == "log")


@pytest.mark.parametrize("fmt, pil_format", [("webp", "WEBP"), ("png", "PNG"), ("jpg", "JPEG")])
def test_batch_reports_progress_per_image(tmp_path, fmt, pil_format):
    sources = []
    for index, mode in enumerate(["RGB", "L", "P", "CMYK"]):
        path = tmp_path / f"in_{index}.{'tiff' if mode == 'CMYK' else 'bmp' if mode == 'L' else 'png'}"
        Image.new(mode, (20, 10)).save(path)
        sources.append(path)

    outputs, _, events = run("image_convert", sources, tmp_path / "out", format=fmt, quality="max")

    assert len(outputs) == 4 and len(set(outputs)) == 4
    for out in outputs:
        with Image.open(out) as image:
            assert image.format == pil_format
    percents = [e["percent"] for e in events if e["type"] == "progress"]
    assert percents == [0, 25, 50, 75, 100]


def test_webp_keeps_alpha(tmp_path):
    outputs, _, _ = run("image_convert", [_rgba_png(tmp_path, "a.png")], tmp_path / "out", format="webp", quality=90)
    with Image.open(outputs[0]) as out:
        assert out.mode == "RGBA" and out.getpixel((1, 1))[3] == 0


def test_quality_changes_jpeg_size(tmp_path):
    source = tmp_path / "noise.png"
    Image.effect_noise((200, 200), 80).convert("RGB").save(source)
    (low,), _, _ = run("image_convert", [source], tmp_path / "low", format="jpg", quality="fast")
    (high,), _, _ = run("image_convert", [source], tmp_path / "high", format="jpg", quality="max")
    assert low.stat().st_size < high.stat().st_size


def test_never_overwrites_input_with_same_extension(tmp_path):
    source = tmp_path / "foto.jpg"
    Image.new("RGB", (10, 10), "green").save(source)
    before = source.read_bytes()
    outputs, _, _ = run("image_convert", [source], tmp_path, format="jpg")
    assert outputs[0] != source and source.read_bytes() == before


@pytest.mark.parametrize("options, code", [({"format": "gif"}, "INVALID_TASK"), ({"format": "jpg", "quality": 0}, "INVALID_TASK")])
def test_invalid_options(tmp_path, options, code):
    source = tmp_path / "a.png"
    Image.new("RGB", (5, 5)).save(source)
    with pytest.raises(EngineError) as error:
        run("image_convert", [source], tmp_path / "out", **options)
    assert error.value.code == code


def test_corrupt_image_is_a_clean_error(tmp_path):
    source = tmp_path / "roto.png"
    source.write_bytes(b"not an image")
    with pytest.raises(EngineError) as error:
        run("image_convert", [source], tmp_path / "out", format="jpg")
    assert error.value.code == "CONVERSION_FAILED"


def test_images_to_pdf_accepts_webp_and_still_merges(tmp_path):
    webp = tmp_path / "uno.webp"
    Image.new("RGB", (100, 50), "red").save(webp)
    png = tmp_path / "dos.png"
    Image.new("RGB", (80, 80), "blue").save(png)

    outputs, meta, _ = run("images_to_pdf", [webp, png], tmp_path / "out", pageSize="fit", margin=0)

    assert meta == {"pages": 2}
    doc = fitz.open(outputs[0])
    try:
        assert len(doc) == 2
        assert len(doc[0].get_images()) == 1 and len(doc[1].get_images()) == 1
        assert round(doc[0].rect.width) == 100 and round(doc[1].rect.width) == 80
    finally:
        doc.close()

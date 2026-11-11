"""Image -> image transcoding (PNG, JPG, WebP) with Pillow.

Exposed as ``stirling_core.image_convert`` so the task contract (engine names) stays unchanged
across Python, TypeScript and Rust."""
from __future__ import annotations

import io
from pathlib import Path

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.paths import atomic_write_bytes, output_path, require_inputs, safe_stem

TARGETS = {"png": ("PNG", ".png"), "jpg": ("JPEG", ".jpg"), "jpeg": ("JPEG", ".jpg"), "webp": ("WEBP", ".webp")}

# UI presets -> encoder settings. Numbers are accepted too (1-100).
QUALITY_PRESETS = {"fast": 70, "balanced": 85, "max": 95}
DEFAULT_QUALITY = 85


def _pil():
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - pillow is a core dependency
        raise EngineError("DEPENDENCY_MISSING", "Pillow is not installed", str(exc)) from exc
    return Image, ImageOps


def parse_quality(raw) -> int:
    if raw is None or raw == "":
        return DEFAULT_QUALITY
    if isinstance(raw, str) and raw.strip().lower() in QUALITY_PRESETS:
        return QUALITY_PRESETS[raw.strip().lower()]
    try:
        value = int(float(raw))
    except (TypeError, ValueError) as exc:
        raise EngineError("INVALID_TASK", "quality must be 1-100 or fast/balanced/max", str(raw)) from exc
    if not 1 <= value <= 100:
        raise EngineError("INVALID_TASK", "quality must be between 1 and 100", str(raw))
    return value


def _has_alpha(image) -> bool:
    return image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)


def _flatten_on_white(image):
    Image, _ = _pil()
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def prepare_mode(image, pil_format: str):
    """Return an image in a mode the target encoder accepts."""
    if image.mode in ("I;16", "I;16B", "I;16L", "I"):
        # 16/32-bit greyscale: scale to 8 bits instead of clipping to white.
        image = image.convert("I").point(lambda value: value * (1 / 256)).convert("L")
    elif image.mode == "F":
        image = image.convert("L")
    if pil_format == "JPEG":
        if _has_alpha(image):
            return _flatten_on_white(image)  # JPEG has no alpha: composite on white
        return image if image.mode in ("RGB", "L", "CMYK") else image.convert("RGB")
    if pil_format == "WEBP":
        if _has_alpha(image):
            return image if image.mode == "RGBA" else image.convert("RGBA")
        return image if image.mode == "RGB" else image.convert("RGB")
    # PNG: no CMYK; keep palette/greyscale/alpha as they are.
    if image.mode == "CMYK":
        return image.convert("RGB")
    if image.mode not in ("1", "L", "LA", "P", "RGB", "RGBA"):
        return image.convert("RGBA" if _has_alpha(image) else "RGB")
    return image


def encode(image, pil_format: str, quality: int, *, dpi=None, icc_profile=None) -> bytes:
    params: dict = {}
    if dpi:
        params["dpi"] = tuple(float(v) for v in dpi[:2])
    if icc_profile and image.mode in ("RGB", "RGBA", "L", "CMYK"):
        params["icc_profile"] = icc_profile
    if pil_format == "JPEG":
        params.update(quality=quality, optimize=True, progressive=quality >= 85, subsampling=0 if quality >= 90 else 2)
    elif pil_format == "WEBP":
        params.update(quality=quality, method=6 if quality >= 90 else 4 if quality >= 80 else 2)
    else:  # PNG is lossless: "quality" only trades speed for size
        params.update(optimize=quality >= 90, compress_level=9 if quality >= 90 else 6 if quality >= 80 else 1)
    buffer = io.BytesIO()
    image.save(buffer, format=pil_format, **params)
    return buffer.getvalue()


def load_rgb_png_bytes(path: Path) -> bytes:
    """Decode any Pillow-readable image to PNG bytes (used when PyMuPDF cannot read it, e.g. WebP)."""
    Image, ImageOps = _pil()
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image = prepare_mode(image, "PNG")
        return encode(image, "PNG", DEFAULT_QUALITY, dpi=image.info.get("dpi"))


class ImageConvertProcessor(BaseProcessor):
    engine_name = "stirling_core"

    @action()
    def image_convert(self, task, reporter):
        Image, ImageOps = _pil()
        inputs = require_inputs(task)
        target = str(task.options.get("format", "")).lower().lstrip(".")
        if target not in TARGETS:
            raise EngineError("INVALID_TASK", "image_convert.format must be png, jpg or webp", target or "(vacío)")
        pil_format, extension = TARGETS[target]
        quality = parse_quality(task.options.get("quality"))

        total = len(inputs)
        outputs: list[str] = []
        reporter.report(0, f"Convirtiendo {total} imagen(es) a {target.upper()}...")
        for index, source in enumerate(inputs):
            reporter.check_cancelled()
            try:
                with Image.open(source) as opened:
                    frames = getattr(opened, "n_frames", 1)
                    if frames > 1:
                        reporter.log(f"{source.name}: {frames} fotogramas; se convierte solo el primero", "warn")
                    info = dict(opened.info)
                    image = ImageOps.exif_transpose(opened)
                    image.load()
            except EngineError:
                raise
            except Exception as exc:  # corrupt or unsupported file
                raise EngineError("CONVERSION_FAILED", f"No se pudo leer {source.name}", f"{type(exc).__name__}: {exc}") from exc

            if pil_format == "JPEG" and _has_alpha(image):
                reporter.log(f"{source.name}: transparencia sustituida por fondo blanco (JPG no admite canal alfa)")
            prepared = prepare_mode(image, pil_format)
            data = encode(prepared, pil_format, quality, dpi=info.get("dpi"), icc_profile=info.get("icc_profile"))
            out = output_path(task, safe_stem(source), "image_convert", extension, index if total > 1 else None)
            atomic_write_bytes(out, data)
            outputs.append(str(out))
            reporter.report((index + 1) * 100 / total, f"Convertida {source.name} ({index + 1}/{total})")
        return outputs, {"format": target, "quality": quality, "count": len(outputs)}

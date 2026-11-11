"""Page metadata, thumbnails and page renders with a two-level cache (memory LRU + disk).

Design (ARCHITECTURE.md §6.2):
  * file hash = sha1(abs path + size + mtime_ns): identifies a PDF version without reading it.
  * disk cache:  <tmp>/docforge_thumbs/<hash>/<maxWidth>/<index>.<fmt>
  * memory LRU of encoded image bytes, and LRU of open PyMuPDF documents, each with its own
    lock (a document must not be used from two threads at once).
  * metadata never renders: page sizes only, fast even for 1000+ page PDFs.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import shutil
import tempfile
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from ..errors import EngineError

CACHE_ROOT = Path(tempfile.gettempdir()) / "docforge_thumbs"
CACHE_MAX_AGE_SEC = 7 * 24 * 3600
MAX_DPI = 150  # legacy default cap (tier "M")
MAX_BATCH = 24
_MIME = {"webp": "image/webp", "png": "image/png", "jpg": "image/jpeg"}

# Resolution tiers. min_dpi guarantees sharp text for reading sizes regardless of the requested
# width (the UI displays the image scaled down to the card); max_dpi bounds memory/CPU.
#   S/M   -> width-driven, cheap overview thumbnails
#   L/XL  -> >= 144 DPI (zoom 2.0): body text readable on the card
#   modal -> >= 144 DPI, up to 216 DPI (zoom 3.0) when a large/HiDPI viewport asks for it
TIERS: dict[str, tuple[float, float]] = {
    "S": (0.0, 110.0),
    "M": (0.0, float(MAX_DPI)),
    "L": (144.0, 160.0),
    "XL": (144.0, 192.0),
    "modal": (144.0, 216.0),
}
DEFAULT_TIER = "M"


def normalize_tier(tier: str | None) -> str:
    if tier is None or tier == "":
        return DEFAULT_TIER
    if tier not in TIERS:
        raise EngineError("INVALID_TASK", f"tier inválido: {tier!r} (use {', '.join(TIERS)})")
    return tier


def zoom_for(page_width_pt: float, max_width_px: int, tier: str) -> float:
    """Zoom factor (1.0 = 72 DPI): width-driven, clamped to the tier's [min_dpi, max_dpi]."""
    min_dpi, max_dpi = TIERS[tier]
    zoom = max_width_px / max(page_width_pt, 1.0)
    return max(min_dpi / 72.0, min(zoom, max_dpi / 72.0))


def _pymupdf():
    try:
        import pymupdf

        return pymupdf
    except ImportError as exc:  # pragma: no cover - dependency is part of the [pdf] extra
        raise EngineError("DEPENDENCY_MISSING", "PyMuPDF is required for thumbnails", str(exc)) from exc


_fitz = _pymupdf


def file_hash(pdf_path: str | Path) -> str:
    path = Path(os.path.abspath(pdf_path))
    try:
        stat = path.stat()
    except OSError as exc:
        raise EngineError("INPUT_NOT_FOUND", f"Archivo no encontrado: {path}", str(exc)) from exc
    key = f"{os.path.normcase(str(path))}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _password_cache_key(password: str | None) -> str:
    if password is None:
        return ""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class _LRU:
    def __init__(self, capacity: int, on_evict=None):
        self.capacity = capacity
        self.on_evict = on_evict
        self._data: OrderedDict[Any, Any] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key, value) -> None:
        evicted = []
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.capacity:
                evicted.append(self._data.popitem(last=False)[1])
        if self.on_evict:
            for item in evicted:
                self.on_evict(item)


class _OpenDoc:
    def __init__(self, doc):
        self.doc = doc
        self.lock = threading.Lock()


def _close_doc(entry: _OpenDoc) -> None:
    with entry.lock:
        try:
            entry.doc.close()
        except Exception:
            pass


class ThumbnailService:
    def __init__(self, cache_root: Path = CACHE_ROOT, doc_capacity: int = 8, image_capacity: int = 256):
        self.cache_root = Path(cache_root)
        self._docs = _LRU(doc_capacity, on_evict=_close_doc)
        self._images = _LRU(image_capacity)
        self._open_lock = threading.Lock()

    # ------------------------------------------------------------------ documents
    def _document(self, pdf_path: str | Path, password: str | None = None) -> tuple[str, _OpenDoc]:
        path = Path(os.path.abspath(pdf_path))
        if not path.is_file():
            raise EngineError("INPUT_NOT_FOUND", f"Archivo no encontrado: {path}")
        digest = file_hash(path)
        document_key = (digest, _password_cache_key(password))
        entry = self._docs.get(document_key)
        if entry is not None:
            return digest, entry
        with self._open_lock:
            entry = self._docs.get(document_key)
            if entry is not None:
                return digest, entry
            fitz = _fitz()
            try:
                doc = fitz.open(str(path))
            except Exception as exc:
                raise EngineError("INVALID_TASK", f"No se pudo abrir el PDF: {path.name}", str(exc)) from exc
            if doc.needs_pass:
                if not password or not doc.authenticate(password):
                    doc.close()
                    raise EngineError("WRONG_PASSWORD", f"El PDF está protegido con contraseña: {path.name}")
            entry = _OpenDoc(doc)
            # Passwords are represented only by a digest in the cache key. A
            # passwordless call therefore cannot reuse an authenticated document.
            self._docs.put(document_key, entry)
            return digest, entry

    # ------------------------------------------------------------------ metadata
    def metadata(self, pdf_path: str, password: str | None = None) -> dict[str, Any]:
        digest, entry = self._document(pdf_path, password)
        with entry.lock:
            pages = []
            for index in range(entry.doc.page_count):
                page = entry.doc[index]
                rect = page.rect  # already reflects /Rotate
                pages.append({
                    "index": index,
                    "width": round(rect.width, 2),
                    "height": round(rect.height, 2),
                    "rotation": page.rotation,
                })
        return {"fileHash": digest, "pageCount": len(pages), "pages": pages}

    # ------------------------------------------------------------------ rendering
    def _zoom(self, entry: _OpenDoc, index: int, max_width: int, tier: str) -> float:
        with entry.lock:
            if index < 0 or index >= entry.doc.page_count:
                raise EngineError("INVALID_TASK", f"Página fuera de rango: {index}")
            return zoom_for(entry.doc[index].rect.width, max_width, tier)

    def _render(self, entry: _OpenDoc, index: int, zoom: float, fmt: str) -> tuple[bytes, int, int, str]:
        fitz = _fitz()
        with entry.lock:
            if index < 0 or index >= entry.doc.page_count:
                raise EngineError("INVALID_TASK", f"Página fuera de rango: {index}")
            page = entry.doc[index]
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            width, height = pix.width, pix.height
            png = pix.tobytes("png")
        if fmt == "png":
            return png, width, height, "png"
        try:
            from PIL import Image

            image = Image.open(io.BytesIO(png))
            buffer = io.BytesIO()
            if fmt == "jpg":
                image.convert("RGB").save(buffer, "JPEG", quality=82)
            else:
                image.save(buffer, "WEBP", quality=80, method=4)
            return buffer.getvalue(), width, height, fmt
        except Exception:
            return png, width, height, "png"  # Pillow without WebP support -> PNG fallback

    def image(self, pdf_path: str, index: int, max_width: int = 300, fmt: str = "webp",
              password: str | None = None, tier: str | None = None) -> dict[str, Any]:
        fmt = fmt if fmt in _MIME else "webp"
        tier = normalize_tier(tier)
        max_width = max(32, min(int(max_width), 2400))
        digest, entry = self._document(pdf_path, password)
        zoom = self._zoom(entry, index, max_width, tier)
        dpi = int(round(zoom * 72))
        cache_digest = digest if password is None else f"{digest}-{_password_cache_key(password)}"
        variant = f"{tier}_{max_width}_{dpi}"  # cache key: hash / tier_width_dpi / index
        key = (cache_digest, variant, index, fmt)
        cached = self._images.get(key)
        if cached is None:
            cached = self._from_disk(cache_digest, variant, index, fmt)
        if cached is None:
            cached = self._render(entry, index, zoom, fmt)
            self._to_disk(cache_digest, variant, index, fmt, cached)
        self._images.put(key, cached)
        data, width, height, real_fmt = cached
        url = f"data:{_MIME[real_fmt]};base64,{base64.b64encode(data).decode('ascii')}"
        return {"index": index, "url": url, "width": width, "height": height, "dpi": dpi, "tier": tier}

    def thumbnails(self, pdf_path: str, start: int, count: int, max_width: int = 300, fmt: str = "webp",
                   password: str | None = None, tier: str | None = None) -> list[dict[str, Any]]:
        count = int(count)
        if count < 1 or count > MAX_BATCH:
            raise EngineError("INVALID_TASK", f"count debe estar entre 1 y {MAX_BATCH}")
        if tier == "modal":
            raise EngineError("INVALID_TASK", "tier 'modal' solo es válido en render_page")
        _, entry = self._document(pdf_path, password)
        total = entry.doc.page_count
        start = max(0, int(start))
        return [self.image(pdf_path, i, max_width, fmt, password, tier) for i in range(start, min(start + count, total))]

    # ------------------------------------------------------------------ disk cache
    def _disk_path(self, digest: str, variant: str, index: int, fmt: str) -> Path:
        return self.cache_root / digest / variant / f"{index}.{fmt}"

    def _from_disk(self, digest: str, variant: str, index: int, fmt: str):
        path = self._disk_path(digest, variant, index, fmt)
        meta = path.with_suffix(path.suffix + ".meta")
        try:
            width, height, real_fmt = meta.read_text(encoding="ascii").split()
            return path.read_bytes(), int(width), int(height), real_fmt
        except (OSError, ValueError):
            return None

    def _to_disk(self, digest: str, variant: str, index: int, fmt: str, value) -> None:
        data, width, height, real_fmt = value
        path = self._disk_path(digest, variant, index, fmt)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(f".{path.name}.{threading.get_ident()}.tmp")
            temp.write_bytes(data)
            os.replace(temp, path)
            path.with_suffix(path.suffix + ".meta").write_text(f"{width} {height} {real_fmt}", encoding="ascii")
        except OSError:
            pass  # cache is best-effort

    def cleanup(self, max_age_sec: float = CACHE_MAX_AGE_SEC) -> int:
        """Delete per-file cache folders not touched for max_age_sec. Returns how many were removed."""
        removed = 0
        if not self.cache_root.is_dir():
            return 0
        limit = time.time() - max_age_sec
        for folder in self.cache_root.iterdir():
            try:
                if folder.is_dir() and folder.stat().st_mtime < limit:
                    shutil.rmtree(folder, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
        return removed


_service: ThumbnailService | None = None
_service_lock = threading.Lock()


def get_service() -> ThumbnailService:
    global _service
    with _service_lock:
        if _service is None:
            _service = ThumbnailService()
        return _service


def get_pdf_pages_metadata(pdf_path: str, password: str | None = None) -> dict[str, Any]:
    return get_service().metadata(pdf_path, password)

"""Rendering of a datasheet page into a PNG.

The API renders the requested page as a high-quality PNG (default 150 dpi)
and caches the rendered image on disk and in memory for instant subsequent
serving to the frontend (FR-12).
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from shared.config import resolve_pdf_path

logger = logging.getLogger(__name__)

#: The resolution of the rendered page.
DEFAULT_DPI = 150

# In-memory LRU cache for fast access to recent pages
_PAGE_CACHE: dict[str, bytes] = {}
_MAX_CACHE_ENTRIES = 128


def _get_page_cache_path(pdf_file: Path, page: int, dpi: int) -> Path:
    cache_dir = pdf_file.parent / ".rendered_pages"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{pdf_file.stem}_p{page}_{dpi}.png"


def render_page_png(
    pdf_path: str | None,
    page: int,
    dpi: int = DEFAULT_DPI,
) -> bytes | None:
    """Render page ``page`` (1-based) of a PDF as PNG bytes with disk & memory caching."""
    if not pdf_path or page < 1:
        return None
    resolved = resolve_pdf_path(pdf_path)
    if not resolved or not resolved.is_file():
        return None

    cache_key = f"{resolved.stem}:{page}:{dpi}"
    if cache_key in _PAGE_CACHE:
        return _PAGE_CACHE[cache_key]

    # Check on-disk cache
    disk_cache = _get_page_cache_path(resolved, page, dpi)
    if disk_cache.is_file():
        try:
            cached_bytes = disk_cache.read_bytes()
            if cached_bytes:
                if len(_PAGE_CACHE) >= _MAX_CACHE_ENTRIES:
                    _PAGE_CACHE.pop(next(iter(_PAGE_CACHE)))
                _PAGE_CACHE[cache_key] = cached_bytes
                return cached_bytes
        except Exception as exc:
            logger.debug("Could not read cached page PNG %s: %s", disk_cache, exc)

    try:
        import pymupdf

        zoom = max(1.0, dpi / 72.0)
        with pymupdf.open(resolved) as document:
            if page > document.page_count:
                return None
            pdf_page = document[page - 1]
            pixmap = pdf_page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            png_bytes = pixmap.tobytes("png")

            # Save to disk cache asynchronously / directly
            try:
                disk_cache.write_bytes(png_bytes)
            except Exception as exc:
                logger.debug("Could not write page cache %s: %s", disk_cache, exc)

            if len(_PAGE_CACHE) >= _MAX_CACHE_ENTRIES:
                _PAGE_CACHE.pop(next(iter(_PAGE_CACHE)))
            _PAGE_CACHE[cache_key] = png_bytes
            return png_bytes
    except Exception as exc:  # pragma: no cover - a broken PDF must not kill the API
        logger.warning("Rendering PDF page %d for %s failed: %s", page, pdf_path, exc)
        return None


__all__ = ["DEFAULT_DPI", "render_page_png"]


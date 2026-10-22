"""Rendering of a datasheet page into a PNG.

The API never ships a PDF to the browser: it renders the requested page as a
PNG (about 150 dpi) so the frontend can show the datasheet page next to the
value it belongs to (FR-12).

PyMuPDF is imported lazily so that the API starts even when the PDF extras
are missing.
"""

from __future__ import annotations

from pathlib import Path

#: The resolution of the rendered page.
DEFAULT_DPI = 150


def render_page_png(
    pdf_path: str | None,
    page: int,
    dpi: int = DEFAULT_DPI,
) -> bytes | None:
    """Render page ``page`` (1-based) of a PDF as PNG bytes.

    Returns ``None`` when the file does not exist, the page does not exist or
    the PDF cannot be opened.
    """
    if not pdf_path or page < 1:
        return None
    path = Path(pdf_path)
    if not path.exists() or not path.is_file():
        return None
    try:
        import pymupdf

        zoom = max(1.0, dpi / 72.0)
        with pymupdf.open(path) as document:
            if page > document.page_count:
                return None
            pdf_page = document[page - 1]
            pixmap = pdf_page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            return pixmap.tobytes("png")
    except Exception:  # pragma: no cover - a broken PDF must not kill the API
        return None


__all__ = ["DEFAULT_DPI", "render_page_png"]

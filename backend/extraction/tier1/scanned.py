"""Scanned (image only) PDF detection.

Owner: agent b-tier1.
"""

from __future__ import annotations

__all__ = ["is_scanned", "page_text_stats"]

#: A page with fewer characters than this is considered image only.
MIN_CHARS_PER_PAGE = 20


def page_text_stats(pdf_path: str) -> dict[str, float | int]:
    """Return simple text statistics of a PDF (used by the scanner check)."""
    import pymupdf

    pages = 0
    total_chars = 0
    images = 0
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            pages += 1
            total_chars += len((page.get_text() or "").strip())
            try:
                images += len(page.get_images(full=True))
            except Exception:  # pragma: no cover - broken image xref
                pass
    return {
        "pages": pages,
        "chars": total_chars,
        "images": images,
        "chars_per_page": (total_chars / pages) if pages else 0.0,
    }


def is_scanned(pdf_path: str, min_chars_per_page: int = MIN_CHARS_PER_PAGE) -> bool:
    """Return ``True`` when the PDF has (almost) no text layer.

    A scanned datasheet has to be handled by tier 3 (vision); tier 1 must not
    produce any value for it.
    """
    stats = page_text_stats(pdf_path)
    pages = int(stats["pages"])
    if pages == 0:
        return False
    return float(stats["chars_per_page"]) < float(min_chars_per_page)

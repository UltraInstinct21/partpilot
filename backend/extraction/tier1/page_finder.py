"""Find the pages of a datasheet that hold the characteristics tables.

Owner: agent b-tier1.
"""

from __future__ import annotations

import re

__all__ = [
    "CHARACTERISTICS_KEYWORDS",
    "STRONG_KEYWORDS",
    "find_pages",
    "page_texts",
    "part_number_of",
]

#: Keywords that always mark a characteristics / ratings page.
STRONG_KEYWORDS: tuple[str, ...] = (
    "electrical characteristics",
    "absolute maximum ratings",
    "absolute maximum rating",
)

#: Weaker variants; they are also accepted.
CHARACTERISTICS_KEYWORDS: tuple[str, ...] = (
    "characteristics",
    "maximum ratings",
    "absolute maximum",
    "electrical specifications",
    "key specifications",
    "electrical characteristics",
    "absolute maximum ratings",
)

# A part number looks like "PMP100N08" or "PGD35": letters and digits, no spaces.
_MPN_RE = re.compile(r"^[A-Za-z]{1,6}[0-9][0-9A-Za-z._-]{1,24}$")


def page_texts(pdf_path: str) -> list[str]:
    """Return the text of every page (1-based order of the returned list)."""
    import pymupdf

    texts: list[str] = []
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            texts.append(page.get_text() or "")
    return texts


def part_number_of(pdf_path: str) -> str | None:
    """Guess the part number of a datasheet.

    The PDF title is used first; when it is missing the first line of page 1
    is used (datasheets print the part number there).
    """
    import pymupdf

    try:
        with pymupdf.open(pdf_path) as doc:
            meta_title = (doc.metadata or {}).get("title") or ""
    except Exception:  # pragma: no cover - unreadable PDF
        return None

    candidate = meta_title.strip()
    if candidate and _MPN_RE.match(candidate):
        return candidate

    texts = page_texts(pdf_path)
    if not texts:
        return None
    for line in texts[0].splitlines():
        token = line.strip()
        if token and _MPN_RE.match(token):
            return token
    return None


def find_pages(pdf_path: str, part_number: str | None = None) -> list[int]:
    """Return the 1-based page numbers that hold characteristics tables.

    A page is kept when it carries one of the characteristics keywords or when
    it mentions the part number.  The result is in document order and has no
    duplicates.
    """
    texts = page_texts(pdf_path)
    if part_number is None:
        part_number = part_number_of(pdf_path)

    pages: list[int] = []
    for number, text in enumerate(texts, start=1):
        lowered = text.lower()
        hit = any(keyword in lowered for keyword in CHARACTERISTICS_KEYWORDS)
        if not hit and part_number:
            hit = part_number.lower() in lowered
        if hit:
            pages.append(number)
    return pages

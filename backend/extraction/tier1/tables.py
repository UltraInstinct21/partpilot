"""Table extraction with pdfplumber.

Owner: agent b-tier1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .parsing import clean_cell

__all__ = ["ExtractedTable", "extract_tables", "extract_tables_from_rows"]


@dataclass(frozen=True)
class ExtractedTable:
    """One table of a PDF page, normalised to a grid of strings."""

    page: int
    rows: list[list[str]] = field(default_factory=list)
    strategy: str = "lines"

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def n_cols(self) -> int:
        return max((len(row) for row in self.rows), default=0)


def _normalise(rows: list[list[str | None]]) -> list[list[str]]:
    """Normalise a pdfplumber table to a rectangular grid of clean strings."""
    width = max((len(row) for row in rows), default=0)
    grid: list[list[str]] = []
    for row in rows:
        cells = [clean_cell(cell) for cell in row]
        cells += [""] * (width - len(cells))
        grid.append(cells)
    return grid


def extract_tables_from_rows(
    page: int,
    rows: list[list[str | None]],
    strategy: str = "lines",
) -> ExtractedTable | None:
    """Build an :class:`ExtractedTable` from raw pdfplumber rows."""
    grid = _normalise(rows)
    if not any(any(cell for cell in row) for row in grid):
        return None
    return ExtractedTable(page=page, rows=grid, strategy=strategy)


def extract_tables(pdf_path: str, pages: list[int] | None = None) -> list[ExtractedTable]:
    """Extract every table of the given pages (all pages when ``pages`` is None).

    Ruled tables are read with the default strategy.  When a page has no ruled
    table the ``text`` strategy is used as a fallback for unruled tables.
    """
    import pdfplumber

    tables: list[ExtractedTable] = []
    with pdfplumber.open(pdf_path) as pdf:
        wanted = set(pages) if pages else None
        for index, page in enumerate(pdf.pages, start=1):
            if wanted is not None and index not in wanted:
                continue
            found = False
            try:
                ruled = page.extract_tables() or []
            except Exception:  # pragma: no cover - broken ruling lines
                ruled = []
            for rows in ruled:
                table = extract_tables_from_rows(index, rows, strategy="lines")
                if table is not None:
                    tables.append(table)
                    found = True
            if found:
                continue
            try:
                unruled = (
                    page.extract_tables(
                        {
                            "vertical_strategy": "text",
                            "horizontal_strategy": "text",
                        }
                    )
                    or []
                )
            except Exception:  # pragma: no cover - unreadable layout
                unruled = []
            for rows in unruled:
                table = extract_tables_from_rows(index, rows, strategy="text")
                if table is not None:
                    tables.append(table)
    return tables

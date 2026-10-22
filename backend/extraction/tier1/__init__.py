"""Tier 1: rule based extraction from datasheet PDFs.

Public API::

    from extraction.tier1 import PdfTier1Extractor

    extractor = PdfTier1Extractor(source_id="pdf-123")
    result = extractor.extract("datasheet.pdf", Family.MOSFET)

The extractor implements the ``Tier1Extractor`` protocol of
``shared.interfaces``.  Every value it returns carries its provenance
(``source_id``, ``page``, ``method``, ``confidence``, ``condition``) and a
field it could not read is reported in ``failed_fields`` - never guessed.

Owner: agent b-tier1.
"""

from __future__ import annotations

from .extractor import BASE_CONFIDENCE, PdfTier1Extractor
from .extractor import Tier1Extractor as Tier1Extractor
from .namemap import (
    FAMILY_FIELDS,
    STANDARD_NAMES,
    NameMap,
    NameMatch,
    match_name,
    normalise_label,
    normalise_symbol,
)
from .page_finder import find_pages
from .parsing import (
    ParsedValue,
    parse_condition,
    parse_number,
    parse_unit,
    parse_value_cell,
)
from .rows import ParsedRow, TableSchema, detect_schema, parse_row
from .scanned import is_scanned
from .tables import ExtractedTable, extract_tables

__all__ = [
    "BASE_CONFIDENCE",
    "ExtractedTable",
    "FAMILY_FIELDS",
    "NameMap",
    "NameMatch",
    "ParsedRow",
    "ParsedValue",
    "PdfTier1Extractor",
    "STANDARD_NAMES",
    "TableSchema",
    "Tier1Extractor",
    "detect_schema",
    "extract_tables",
    "find_pages",
    "is_scanned",
    "match_name",
    "normalise_label",
    "normalise_symbol",
    "parse_condition",
    "parse_number",
    "parse_row",
    "parse_unit",
    "parse_value_cell",
]

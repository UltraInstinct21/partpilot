"""SQLAlchemy models for PartPilot (CONTRACT v1).

The models mirror ``backend/shared/db_schema.sql`` **exactly**: same table
names, same column names, same types, same CHECK constraints, same UNIQUE
constraints and the same index names.  ``backend/tests/db/test_schema.py``
verifies that the created database is byte-for-byte the same schema as the
reference file, so the two can never drift apart.

Style: SQLAlchemy 2.x (``DeclarativeBase`` + ``Mapped[...]`` /
``mapped_column``).

JSON columns
------------
``parts.source_ids``, ``parameters.condition`` and ``offers.price_breaks`` are
JSON documents.  SQLite has no JSON type, so SQLAlchemy stores them as TEXT -
which is exactly what the reference schema does.

Timestamps
----------
The reference schema stores timestamps as TEXT with ``datetime('now')`` as the
server default.  The ORM writes ISO-8601 strings with an explicit UTC offset
(``2026-01-01T12:00:00.000000+00:00``) so that a round trip through the
repository returns the same aware ``datetime`` that went in.  Both formats are
readable by :func:`db.session.parse_timestamp`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = [
    "Base",
    "LLMCallRow",
    "NameMapRow",
    "OfferRow",
    "ParameterRow",
    "PartRow",
    "ReviewCorrectionRow",
    "SourceRow",
    "utcnow_iso",
]


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


class Base(DeclarativeBase):
    """Declarative base of every PartPilot table."""


class PartRow(Base):
    """``parts`` - one component (plan section 7)."""

    __tablename__ = "parts"
    __table_args__ = (
        CheckConstraint("family IN ('mosfet', 'gate_driver')", name="ck_parts_family"),
        CheckConstraint(
            "lifecycle_status IN ('active', 'nrnd', 'obsolete', 'unknown')",
            name="ck_parts_lifecycle_status",
        ),
        UniqueConstraint("mpn", "manufacturer", name="uq_parts_mpn_manufacturer"),
        Index("idx_parts_family", "family"),
        Index("idx_parts_manufacturer", "manufacturer"),
        Index("idx_parts_package", "package"),
        Index("idx_parts_lifecycle", "lifecycle_status"),
        Index("idx_parts_mpn", "mpn"),
    )

    part_id: Mapped[str] = mapped_column(String, primary_key=True)
    mpn: Mapped[str] = mapped_column(String, nullable=False)
    manufacturer: Mapped[str] = mapped_column(String, nullable=False)
    family: Mapped[str] = mapped_column(String, nullable=False)
    package: Mapped[str | None] = mapped_column(String, nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(
        String, nullable=False, default="unknown", server_default=text("'unknown'")
    )
    datasheet_url: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    source_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utcnow_iso, server_default=text("datetime('now')")
    )
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utcnow_iso, server_default=text("datetime('now')")
    )


class SourceRow(Base):
    """``sources`` - provenance of one fetched artefact."""

    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("type IN ('api', 'pdf', 'manual')", name="ck_sources_type"),
        Index("idx_sources_hash", "file_hash"),
        Index("idx_sources_type", "type"),
    )

    source_id: Mapped[str] = mapped_column(String, primary_key=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    fetched_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utcnow_iso, server_default=text("datetime('now')")
    )
    file_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    distributor: Mapped[str | None] = mapped_column(String, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    local_path: Mapped[str | None] = mapped_column(String, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ParameterRow(Base):
    """``parameters`` - one extracted value with its full provenance."""

    __tablename__ = "parameters"
    __table_args__ = (
        CheckConstraint(
            "method IN ('tier1', 'tier2', 'tier3', 'api', 'manual')",
            name="ck_parameters_method",
        ),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_parameters_confidence"),
        CheckConstraint(
            "status IN ('accepted', 'review', 'rejected')", name="ck_parameters_status"
        ),
        Index("idx_parameters_part", "part_id"),
        Index("idx_parameters_name", "name"),
        Index("idx_parameters_status", "status"),
        Index("idx_parameters_method", "method"),
        Index("idx_parameters_source", "source_id"),
    )

    param_id: Mapped[str] = mapped_column(String, primary_key=True)
    part_id: Mapped[str] = mapped_column(
        String, ForeignKey("parts.part_id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_typ: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    condition: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    source_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("sources.source_id", ondelete="SET NULL"), nullable=True
    )
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    method: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default=text("0.0")
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="review", server_default=text("'review'")
    )
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utcnow_iso, server_default=text("datetime('now')")
    )
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utcnow_iso, server_default=text("datetime('now')")
    )


class OfferRow(Base):
    """``offers`` - distributor price and stock."""

    __tablename__ = "offers"
    __table_args__ = (
        Index("idx_offers_part", "part_id"),
        Index("idx_offers_distributor", "distributor"),
    )

    offer_id: Mapped[str] = mapped_column(String, primary_key=True)
    part_id: Mapped[str] = mapped_column(
        String, ForeignKey("parts.part_id", ondelete="CASCADE"), nullable=False
    )
    distributor: Mapped[str] = mapped_column(String, nullable=False)
    sku: Mapped[str | None] = mapped_column(String, nullable=True)
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(
        String, nullable=False, default="USD", server_default=text("'USD'")
    )
    price_breaks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    fetched_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utcnow_iso, server_default=text("datetime('now')")
    )


class NameMapRow(Base):
    """``name_map`` - raw parameter name -> standard name."""

    __tablename__ = "name_map"
    __table_args__ = (
        CheckConstraint("family IN ('mosfet', 'gate_driver')", name="ck_name_map_family"),
        CheckConstraint("approved IN ('yes', 'no')", name="ck_name_map_approved"),
        UniqueConstraint("raw_name", "family", name="uq_name_map_raw_family"),
        Index("idx_name_map_raw", "raw_name"),
        Index("idx_name_map_standard", "standard_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_name: Mapped[str] = mapped_column(String, nullable=False)
    standard_name: Mapped[str] = mapped_column(String, nullable=False)
    family: Mapped[str | None] = mapped_column(String, nullable=True)
    approved: Mapped[str] = mapped_column(
        String, nullable=False, default="no", server_default=text("'no'")
    )
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utcnow_iso, server_default=text("datetime('now')")
    )


class LLMCallRow(Base):
    """``llm_calls`` - cost and token accounting (NFR-05)."""

    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("idx_llm_calls_chain", "chain"),
        Index("idx_llm_calls_created", "created_at"),
    )

    call_id: Mapped[str] = mapped_column(String, primary_key=True)
    chain: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    tokens_in: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    tokens_out: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    cost: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default=text("0.0")
    )
    prompt_version: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=text("''")
    )
    part_id: Mapped[str | None] = mapped_column(String, nullable=True)
    cached: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utcnow_iso, server_default=text("datetime('now')")
    )


class ReviewCorrectionRow(Base):
    """``review_corrections`` - human corrections feed back into name_map."""

    __tablename__ = "review_corrections"
    __table_args__ = (Index("idx_review_corrections_param", "param_id"),)

    correction_id: Mapped[str] = mapped_column(String, primary_key=True)
    param_id: Mapped[str] = mapped_column(String, nullable=False)
    part_id: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utcnow_iso, server_default=text("datetime('now')")
    )

"""SQLAlchemy implementation of the ``PartsRepository`` protocol (agent E-data).

The repository is the only place that turns a :class:`SearchFilter` into SQL.
The LLM may *build* a filter, the database always *executes* it (plan WP6).

Design notes
------------
* Every value that is read or written carries its provenance: ``source_id``,
  ``page``, ``method``, ``confidence``, ``status`` and ``condition`` survive a
  round trip unchanged (FR-05, FR-09).
* ``list_parts`` returns ``(summaries, total)`` where ``total`` is the number
  of matches **before** ``limit``/``offset`` are applied.
* A ``ParameterConstraint`` is executed as an ``EXISTS`` sub-query on the
  ``parameters`` table.  The comparison happens in the canonical unit: the
  constraint is converted with :mod:`db.units` and the stored value is scaled
  into the canonical unit by a SQL ``CASE`` expression, so a value that was
  stored as ``12 mohm`` matches a constraint of ``5 mohm`` as well as a
  constraint of ``0.005 ohm``.
* A parameter with the status ``rejected`` never satisfies a search
  constraint; ``accepted`` and ``review`` values do.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, Select, and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import (
    LLMCallRow,
    NameMapRow,
    OfferRow,
    ParameterRow,
    PartRow,
    ReviewCorrectionRow,
    SourceRow,
    utcnow_iso,
)
from db.session import make_session_factory, parse_timestamp
from db.units import PARAMETER_UNITS, canonical_unit, canonicalize, unit_scale_map
from shared.schemas import (
    ExtractionMethod,
    Family,
    LifecycleStatus,
    LLMCallRecord,
    Offer,
    ParameterConstraint,
    ParameterValue,
    PartRecord,
    PartSummary,
    ReviewDecision,
    ReviewItem,
    ReviewResponse,
    SearchFilter,
    SourcePage,
    SourceRef,
    SourceType,
    StatsResponse,
    ValueStatus,
)

__all__ = ["KEY_PARAMETERS", "NameMapRepository", "SqlAlchemyPartsRepository"]

#: the values that are shown in a search result row, per family.
KEY_PARAMETERS: dict[str, tuple[str, ...]] = {
    Family.MOSFET.value: (
        "vds_max",
        "id_continuous",
        "rds_on",
        "total_gate_charge_qg",
    ),
    Family.GATE_DRIVER.value: (
        "supply_voltage_min",
        "supply_voltage_max",
        "peak_source_current",
        "propagation_delay",
    ),
}

#: a search constraint is satisfied by these statuses (``rejected`` never).
MATCHABLE_STATUSES = ("accepted", "review")

#: a value below this confidence is worth a human look (FR-10).
REVIEW_CONFIDENCE_THRESHOLD = 0.75


def _new_id() -> str:
    return uuid.uuid4().hex


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like_pattern(text: str) -> str:
    return f"%{_escape_like(text)}%"


def _dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat(timespec="microseconds")


class SqlAlchemyPartsRepository:
    """Repository backed by SQLAlchemy (SQLite in production).

    The constructor accepts either an :class:`~sqlalchemy.Engine` (a session is
    created per call and committed) or an existing
    :class:`~sqlalchemy.orm.Session` (the caller stays in charge of the
    transaction).
    """

    def __init__(self, engine_or_session: Engine | Session) -> None:
        self._engine: Engine | None = None
        self._external_session: Session | None = None
        if isinstance(engine_or_session, Session):
            self._external_session = engine_or_session
        else:
            self._engine = engine_or_session

    # ------------------------------------------------------------------
    # session handling
    # ------------------------------------------------------------------
    @contextmanager
    def _scope(self) -> Iterable[Session]:
        if self._external_session is not None:
            yield self._external_session
            return
        if self._engine is None:  # pragma: no cover - defensive
            raise RuntimeError("the repository has neither an engine nor a session")
        session = make_session_factory(self._engine)()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # row -> model
    # ------------------------------------------------------------------
    @staticmethod
    def _parameter_from_row(row: ParameterRow) -> ParameterValue:
        return ParameterValue(
            param_id=row.param_id,
            part_id=row.part_id,
            name=row.name,
            value=row.value,
            value_min=row.value_min,
            value_typ=row.value_typ,
            value_max=row.value_max,
            unit=row.unit,
            condition=dict(row.condition or {}),
            source_id=row.source_id,
            page=row.page,
            method=ExtractionMethod(row.method) if row.method else None,
            confidence=float(row.confidence or 0.0),
            status=ValueStatus(row.status),
            raw_text=row.raw_text,
            value_text=row.value_text,
        )

    @staticmethod
    def _offer_from_row(row: OfferRow) -> Offer:
        return Offer(
            part_id=row.part_id,
            distributor=row.distributor,
            sku=row.sku,
            stock=row.stock,
            unit_price=row.unit_price,
            currency=row.currency,
            price_breaks=list(row.price_breaks or []),
            lead_time_days=row.lead_time_days,
            fetched_at=parse_timestamp(row.fetched_at),
            url=row.url,
        )

    @staticmethod
    def _source_from_row(row: SourceRow) -> SourceRef:
        return SourceRef(
            source_id=row.source_id,
            url=row.url,
            type=SourceType(row.type),
            fetched_at=parse_timestamp(row.fetched_at) or datetime.now(UTC),
            file_hash=row.file_hash,
            distributor=row.distributor,
            page_count=row.page_count,
            local_path=row.local_path,
            content_type=row.content_type,
            note=row.note,
        )

    @staticmethod
    def _part_from_row(
        row: PartRow,
        parameters: Sequence[ParameterValue],
        offers: Sequence[Offer],
    ) -> PartRecord:
        return PartRecord(
            part_id=row.part_id,
            mpn=row.mpn,
            manufacturer=row.manufacturer,
            family=Family(row.family),
            package=row.package,
            lifecycle_status=LifecycleStatus(row.lifecycle_status),
            datasheet_url=row.datasheet_url,
            description=row.description,
            source_ids=list(row.source_ids or []),
            parameters=list(parameters),
            offers=list(offers),
            updated_at=parse_timestamp(row.updated_at),
        )

    # ------------------------------------------------------------------
    # parts
    # ------------------------------------------------------------------
    def add_part(self, part: PartRecord) -> PartRecord:
        """Insert or update a part together with its values and offers.

        A value that references a source has to be registered with
        :meth:`add_source` first - the reference schema uses a foreign key.
        """
        with self._scope() as session:
            self._check_sources(session, part)
            row = session.get(PartRow, part.part_id)
            now = utcnow_iso()
            if row is None:
                row = PartRow(part_id=part.part_id)
                session.add(row)
            row.mpn = part.mpn
            row.manufacturer = part.manufacturer
            row.family = Family(part.family).value
            row.package = part.package
            row.lifecycle_status = LifecycleStatus(part.lifecycle_status).value
            row.datasheet_url = part.datasheet_url
            row.description = part.description
            row.source_ids = list(part.source_ids)
            row.updated_at = now
            try:
                session.flush()
            except IntegrityError as exc:  # pragma: no cover - defensive
                session.rollback()
                raise ValueError(
                    f"a part with mpn={part.mpn!r} and manufacturer="
                    f"{part.manufacturer!r} already exists"
                ) from exc
            for value in part.parameters:
                self._upsert_parameter(session, part.part_id, value)
            for offer in part.offers:
                self._upsert_offer(session, part.part_id, offer.model_dump())
            session.flush()
        stored = self.get_part(part.part_id)
        if stored is None:  # pragma: no cover - defensive
            raise RuntimeError(f"part {part.part_id} disappeared")
        return stored

    def _check_sources(self, session: Session, part: PartRecord) -> None:
        """Raise a helpful error when a value references an unknown source."""
        wanted = {value.source_id for value in part.parameters if value.source_id is not None}
        if not wanted:
            return
        known = set(
            session.scalars(
                select(SourceRow.source_id).where(SourceRow.source_id.in_(wanted))
            ).all()
        )
        missing = sorted(wanted - known)
        if missing:
            raise ValueError(
                "unknown source_id(s) "
                f"{', '.join(missing)}: register them with add_source() first"
            )

    def _upsert_parameter(
        self, session: Session, part_id: str, value: ParameterValue
    ) -> ParameterRow:
        row: ParameterRow | None = None
        if value.param_id:
            row = session.get(ParameterRow, value.param_id)
        if row is None:
            # idempotent: a value with the same name and unit of the same part
            # is updated instead of duplicated (the seed loader relies on it).
            row = session.scalars(
                select(ParameterRow)
                .where(
                    ParameterRow.part_id == part_id,
                    ParameterRow.name == value.name,
                    (
                        ParameterRow.unit.is_(None)
                        if value.unit is None
                        else ParameterRow.unit == value.unit
                    ),
                )
                .order_by(ParameterRow.created_at, ParameterRow.param_id)
                .limit(1)
            ).first()
        if row is None:
            row = ParameterRow(param_id=value.param_id or _new_id(), part_id=part_id)
            session.add(row)
        row.part_id = part_id
        row.name = value.name
        row.value = value.value
        row.value_min = value.value_min
        row.value_typ = value.value_typ
        row.value_max = value.value_max
        row.unit = value.unit
        row.condition = dict(value.condition or {})
        row.source_id = value.source_id
        row.page = value.page
        row.method = value.method.value if value.method else None
        row.confidence = float(value.confidence)
        row.status = ValueStatus(value.status).value
        row.raw_text = value.raw_text
        row.value_text = value.value_text
        row.updated_at = utcnow_iso()
        session.flush()
        return row

    def get_part(self, part_id: str) -> PartRecord | None:
        """Return one part with **all** of its values (any status) and its offers."""
        with self._scope() as session:
            row = session.get(PartRow, part_id)
            if row is None:
                return None
            parameters = session.scalars(
                select(ParameterRow)
                .where(ParameterRow.part_id == part_id)
                .order_by(ParameterRow.created_at, ParameterRow.param_id)
            ).all()
            offers = session.scalars(select(OfferRow).where(OfferRow.part_id == part_id)).all()
            return self._part_from_row(
                row,
                [self._parameter_from_row(item) for item in parameters],
                [self._offer_from_row(item) for item in offers],
            )

    def get_part_by_mpn(self, mpn: str) -> PartRecord | None:
        """Return the part with this manufacturer part number, if any."""
        with self._scope() as session:
            row = session.scalars(
                select(PartRow)
                .where(PartRow.mpn == mpn)
                .order_by(PartRow.created_at, PartRow.part_id)
                .limit(1)
            ).first()
            if row is None:
                return None
            parameters = session.scalars(
                select(ParameterRow)
                .where(ParameterRow.part_id == row.part_id)
                .order_by(ParameterRow.created_at, ParameterRow.param_id)
            ).all()
            offers = session.scalars(select(OfferRow).where(OfferRow.part_id == row.part_id)).all()
            return self._part_from_row(
                row,
                [self._parameter_from_row(item) for item in parameters],
                [self._offer_from_row(item) for item in offers],
            )

    # ------------------------------------------------------------------
    # search
    # ------------------------------------------------------------------
    def _canonical_value_expression(self):
        """SQL expression that scales ``parameters.value`` into the canonical unit."""
        scales = {unit: factor for unit, factor in unit_scale_map().items() if factor != 1.0}
        if not scales:  # pragma: no cover - defensive
            return ParameterRow.value
        return case(
            *[
                (ParameterRow.unit == unit, ParameterRow.value * factor)
                for unit, factor in scales.items()
            ],
            else_=ParameterRow.value,
        )

    def _parameter_condition(self, constraint: ParameterConstraint) -> Any:
        """Translate one :class:`ParameterConstraint` into a SQL condition."""
        name = constraint.name
        operator = constraint.operator
        lower, upper = constraint.bounds()

        unit = constraint.unit
        if unit:
            canonical = canonical_unit(unit)
            convertible = canonical is not None
        else:
            canonical = PARAMETER_UNITS.get(name)
            convertible = canonical is not None

        value_expression = self._canonical_value_expression() if convertible else ParameterRow.value

        def convert(raw: float | None) -> float | None:
            if raw is None:
                return None
            if unit:
                return canonicalize(raw, unit)[0]
            return raw

        conditions = []
        if operator == "lt":
            threshold = convert(upper)
            if threshold is not None:
                conditions.append(value_expression < threshold)
        elif operator == "lte":
            threshold = convert(upper)
            if threshold is not None:
                conditions.append(value_expression <= threshold)
        elif operator == "gt":
            threshold = convert(lower)
            if threshold is not None:
                conditions.append(value_expression > threshold)
        elif operator == "gte":
            threshold = convert(lower)
            if threshold is not None:
                conditions.append(value_expression >= threshold)
        elif operator == "eq":
            threshold = convert(lower if lower is not None else upper)
            if threshold is not None:
                conditions.append(value_expression == threshold)
        else:  # between
            low = convert(lower if lower is not None else constraint.typ)
            high = convert(upper if upper is not None else constraint.typ)
            if low is not None:
                conditions.append(value_expression >= low)
            if high is not None:
                conditions.append(value_expression <= high)

        sub_query = select(1).where(
            ParameterRow.part_id == PartRow.part_id,
            ParameterRow.name == name,
            ParameterRow.status.in_(MATCHABLE_STATUSES),
            ParameterRow.value.is_not(None),
        )
        if conditions:
            sub_query = sub_query.where(and_(*conditions))
        return sub_query.exists()

    def _filter_conditions(self, filt: SearchFilter | None) -> list[Any]:
        if filt is None:
            return []
        conditions: list[Any] = []
        if filt.family is not None:
            conditions.append(PartRow.family == Family(filt.family).value)
        if filt.manufacturer:
            conditions.append(func.lower(PartRow.manufacturer) == filt.manufacturer.lower())
        if filt.manufacturer_in:
            conditions.append(
                PartRow.manufacturer.in_([name for name in filt.manufacturer_in if name])
            )
        if filt.mpn_contains:
            pattern = _like_pattern(filt.mpn_contains)
            conditions.append(PartRow.mpn.ilike(pattern, escape="\\"))
        if filt.package:
            conditions.append(func.lower(PartRow.package) == filt.package.lower())
        if filt.package_in:
            conditions.append(PartRow.package.in_([name for name in filt.package_in if name]))
        if filt.lifecycle_status:
            conditions.append(
                PartRow.lifecycle_status.in_(
                    [LifecycleStatus(status).value for status in filt.lifecycle_status]
                )
            )
        if filt.in_stock is True:
            conditions.append(
                select(1)
                .where(
                    OfferRow.part_id == PartRow.part_id,
                    OfferRow.stock.is_not(None),
                    OfferRow.stock > 0,
                )
                .exists()
            )
        elif filt.in_stock is False:
            conditions.append(
                ~select(1)
                .where(
                    OfferRow.part_id == PartRow.part_id,
                    OfferRow.stock.is_not(None),
                    OfferRow.stock > 0,
                )
                .exists()
            )
        if filt.text:
            pattern = _like_pattern(filt.text)
            conditions.append(
                or_(
                    PartRow.mpn.ilike(pattern, escape="\\"),
                    PartRow.description.ilike(pattern, escape="\\"),
                    PartRow.manufacturer.ilike(pattern, escape="\\"),
                )
            )
        for constraint in filt.parameters:
            conditions.append(self._parameter_condition(constraint))
        return conditions

    def list_parts(
        self,
        filt: SearchFilter | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PartSummary], int]:
        """Return a page of matching parts and the total number of matches."""
        conditions = self._filter_conditions(filt)
        with self._scope() as session:
            total = int(
                session.scalar(select(func.count()).select_from(PartRow).where(*conditions)) or 0
            )
            query: Select = select(PartRow).where(*conditions)
            query = query.order_by(PartRow.created_at.desc(), PartRow.part_id)
            if limit is not None:
                query = query.limit(max(int(limit), 0))
            if offset:
                query = query.offset(max(int(offset), 0))
            rows = session.scalars(query).all()
            summaries = self._summaries(session, rows)
        return summaries, total

    def _summaries(self, session: Session, rows: Sequence[PartRow]) -> list[PartSummary]:
        if not rows:
            return []
        part_ids = [row.part_id for row in rows]
        names = sorted({name for row in rows for name in KEY_PARAMETERS.get(row.family, ())})
        key_values: dict[tuple[str, str], float | None] = {}
        if names:
            parameter_rows = session.scalars(
                select(ParameterRow)
                .where(
                    ParameterRow.part_id.in_(part_ids),
                    ParameterRow.name.in_(names),
                    ParameterRow.status == ValueStatus.ACCEPTED.value,
                )
                .order_by(ParameterRow.confidence.desc(), ParameterRow.created_at)
            ).all()
            for parameter_row in parameter_rows:
                key = (parameter_row.part_id, parameter_row.name)
                if key in key_values:
                    continue
                key_values[key] = _representative(
                    parameter_row.value,
                    parameter_row.value_typ,
                    parameter_row.value_max,
                    parameter_row.value_min,
                )
        offer_rows = session.scalars(select(OfferRow).where(OfferRow.part_id.in_(part_ids))).all()
        offers_count: dict[str, int] = {}
        total_stock: dict[str, int] = {}
        for offer_row in offer_rows:
            offers_count[offer_row.part_id] = offers_count.get(offer_row.part_id, 0) + 1
            total_stock[offer_row.part_id] = total_stock.get(offer_row.part_id, 0) + int(
                offer_row.stock or 0
            )
        summaries = []
        for row in rows:
            key_parameters = {
                name: key_values.get((row.part_id, name))
                for name in KEY_PARAMETERS.get(row.family, ())
            }
            summaries.append(
                PartSummary(
                    part_id=row.part_id,
                    mpn=row.mpn,
                    manufacturer=row.manufacturer,
                    family=Family(row.family),
                    package=row.package,
                    lifecycle_status=LifecycleStatus(row.lifecycle_status),
                    datasheet_url=row.datasheet_url,
                    description=row.description,
                    key_parameters=key_parameters,
                    offers_count=offers_count.get(row.part_id, 0),
                    total_stock=total_stock.get(row.part_id, 0),
                )
            )
        return summaries

    # ------------------------------------------------------------------
    # parameters
    # ------------------------------------------------------------------
    def get_parameters(self, part_id: str) -> list[ParameterValue]:
        """Return every stored value of a part (any status)."""
        with self._scope() as session:
            rows = session.scalars(
                select(ParameterRow)
                .where(ParameterRow.part_id == part_id)
                .order_by(ParameterRow.created_at, ParameterRow.param_id)
            ).all()
            return [self._parameter_from_row(row) for row in rows]

    def get_parameter(self, param_id: str) -> ParameterValue | None:
        """Return one value by id."""
        with self._scope() as session:
            row = session.get(ParameterRow, param_id)
            return None if row is None else self._parameter_from_row(row)

    def update_parameter(self, value: ParameterValue) -> ParameterValue:
        """Persist a changed value (a validation result or a human correction)."""
        if not value.param_id:
            raise ValueError("a parameter needs a param_id to be updated")
        with self._scope() as session:
            row = session.get(ParameterRow, value.param_id)
            if row is None:
                raise KeyError(value.param_id)
            row.name = value.name
            row.value = value.value
            row.value_min = value.value_min
            row.value_typ = value.value_typ
            row.value_max = value.value_max
            row.unit = value.unit
            row.condition = dict(value.condition or {})
            row.source_id = value.source_id
            row.page = value.page
            row.method = value.method.value if value.method else None
            row.confidence = float(value.confidence)
            row.status = ValueStatus(value.status).value
            row.raw_text = value.raw_text
            row.value_text = value.value_text
            row.updated_at = utcnow_iso()
            session.flush()
            return self._parameter_from_row(row)

    # ------------------------------------------------------------------
    # sources
    # ------------------------------------------------------------------
    def add_source(self, source: SourceRef) -> SourceRef:
        """Insert or update a source record."""
        with self._scope() as session:
            row = session.get(SourceRow, source.source_id)
            if row is None:
                row = SourceRow(source_id=source.source_id)
                session.add(row)
            row.url = source.url
            row.type = SourceType(source.type).value
            row.fetched_at = _dt(source.fetched_at) or utcnow_iso()
            row.file_hash = source.file_hash
            row.distributor = source.distributor
            row.page_count = source.page_count
            row.local_path = source.local_path
            row.content_type = source.content_type
            row.note = source.note
            session.flush()
            return self._source_from_row(row)

    def get_source(self, source_id: str) -> SourceRef | None:
        """Return one source by id."""
        with self._scope() as session:
            row = session.get(SourceRow, source_id)
            return None if row is None else self._source_from_row(row)

    def get_source_page(self, source_id: str, page: int) -> SourcePage | None:
        """Return one page of a source.

        The page text is looked up in this order:

        1. the page cache that :meth:`add_source_page` writes into the
           ``sources.note`` field (a JSON document);
        2. the local PDF (``sources.local_path``) when the file is still on
           disk - the text layer is read with PyMuPDF;
        3. nothing: a :class:`SourcePage` without text is returned.

        ``None`` is only returned when the source itself does not exist.
        """
        with self._scope() as session:
            row = session.get(SourceRow, source_id)
            if row is None:
                return None
            cached = self._cached_pages(row.note).get(str(page))
            local_path = row.local_path
        if cached:
            return SourcePage(
                source_id=source_id,
                page=page,
                width=cached.get("width"),
                height=cached.get("height"),
                text=cached.get("text"),
                image_url=cached.get("image_url"),
                is_image_only=bool(cached.get("is_image_only", False)),
            )
        extracted = self._read_pdf_page(local_path, page)
        if extracted is not None:
            return extracted
        return SourcePage(source_id=source_id, page=page)

    def add_source_page(
        self,
        source_id: str,
        page: int,
        text: str | None = None,
        *,
        width: int | None = None,
        height: int | None = None,
        image_url: str | None = None,
        is_image_only: bool = False,
    ) -> SourcePage | None:
        """Cache the text of one page in the ``sources.note`` field.

        The note field holds a JSON document::

            {"note": "<the original free text>",
             "pages": {"1": {"text": "...", "width": 612, "height": 792}}}
        """
        with self._scope() as session:
            row = session.get(SourceRow, source_id)
            if row is None:
                return None
            document = self._note_document(row.note)
            pages = document.setdefault("pages", {})
            pages[str(page)] = {
                "text": text,
                "width": width,
                "height": height,
                "image_url": image_url,
                "is_image_only": bool(is_image_only),
            }
            row.note = json.dumps(document, ensure_ascii=False)
            session.flush()
        return SourcePage(
            source_id=source_id,
            page=page,
            width=width,
            height=height,
            text=text,
            image_url=image_url,
            is_image_only=is_image_only,
        )

    @staticmethod
    def _note_document(note: str | None) -> dict[str, Any]:
        if not note:
            return {}
        try:
            document = json.loads(note)
        except (TypeError, ValueError):
            return {"note": note}
        if not isinstance(document, dict):
            return {"note": note}
        return document

    @classmethod
    def _cached_pages(cls, note: str | None) -> dict[str, Any]:
        pages = cls._note_document(note).get("pages")
        return pages if isinstance(pages, dict) else {}

    @staticmethod
    def _read_pdf_page(local_path: str | None, page: int) -> SourcePage | None:
        if not local_path:
            return None
        path = Path(local_path).expanduser()
        if not path.is_file():
            return None
        try:
            import pymupdf
        except ImportError:  # pragma: no cover - pymupdf is a hard dependency
            return None
        try:
            with pymupdf.open(path) as document:
                if page < 1 or page > document.page_count:
                    return None
                pdf_page = document[page - 1]
                text = pdf_page.get_text()
                return SourcePage(
                    source_id="",
                    page=page,
                    width=int(pdf_page.rect.width),
                    height=int(pdf_page.rect.height),
                    text=text,
                    is_image_only=not text.strip(),
                )
        except Exception:  # pragma: no cover - a broken PDF must not break the API
            return None

    # ------------------------------------------------------------------
    # offers
    # ------------------------------------------------------------------
    def add_offer(self, part_id: str, offer: dict[str, Any]) -> None:
        """Store one distributor offer for a part."""
        payload = dict(offer)
        payload.setdefault("part_id", part_id)
        model = Offer.model_validate(payload)
        data = model.model_dump()
        data["part_id"] = part_id
        if offer.get("offer_id"):
            data["offer_id"] = offer["offer_id"]
        with self._scope() as session:
            self._upsert_offer(session, part_id, data)

    def _upsert_offer(self, session: Session, part_id: str, payload: dict[str, Any]) -> OfferRow:
        offer_id = payload.get("offer_id")
        row: OfferRow | None = None
        if offer_id:
            row = session.get(OfferRow, offer_id)
        if row is None:
            row = session.scalars(
                select(OfferRow)
                .where(
                    OfferRow.part_id == part_id,
                    OfferRow.distributor == payload.get("distributor", ""),
                    (
                        OfferRow.sku.is_(None)
                        if payload.get("sku") is None
                        else OfferRow.sku == payload.get("sku")
                    ),
                )
                .order_by(OfferRow.fetched_at)
                .limit(1)
            ).first()
        if row is None:
            row = OfferRow(offer_id=offer_id or _new_id(), part_id=part_id)
            session.add(row)
        row.part_id = part_id
        row.distributor = payload.get("distributor") or ""
        row.sku = payload.get("sku")
        stock = payload.get("stock")
        row.stock = None if stock is None else int(stock)
        row.unit_price = payload.get("unit_price")
        row.currency = payload.get("currency") or "USD"
        row.price_breaks = list(payload.get("price_breaks") or [])
        row.lead_time_days = payload.get("lead_time_days")
        row.url = payload.get("url")
        fetched_at = payload.get("fetched_at")
        row.fetched_at = _dt(fetched_at) if isinstance(fetched_at, datetime) else utcnow_iso()
        session.flush()
        return row

    # ------------------------------------------------------------------
    # review queue
    # ------------------------------------------------------------------
    def list_review_queue(self, limit: int = 50, offset: int = 0) -> list[ReviewItem]:
        """Return the values waiting for a human, least confident first."""
        with self._scope() as session:
            query = (
                select(ParameterRow, PartRow)
                .join(PartRow, PartRow.part_id == ParameterRow.part_id)
                .where(ParameterRow.status == ValueStatus.REVIEW.value)
                .order_by(ParameterRow.confidence, ParameterRow.created_at, ParameterRow.param_id)
            )
            if limit is not None:
                query = query.limit(max(int(limit), 0))
            if offset:
                query = query.offset(max(int(offset), 0))
            rows = session.execute(query).all()
            return [self._review_item(parameter_row, part_row) for parameter_row, part_row in rows]

    @staticmethod
    def _review_item(parameter_row: ParameterRow, part_row: PartRow) -> ReviewItem:
        reasons: list[str] = []
        if parameter_row.confidence < REVIEW_CONFIDENCE_THRESHOLD:
            reasons.append(
                f"confidence {parameter_row.confidence:.2f} is below "
                f"{REVIEW_CONFIDENCE_THRESHOLD:.2f}"
            )
        if parameter_row.source_id is None:
            reasons.append("the value has no source")
        return ReviewItem(
            param_id=parameter_row.param_id,
            part_id=part_row.part_id,
            mpn=part_row.mpn,
            manufacturer=part_row.manufacturer,
            family=Family(part_row.family),
            name=parameter_row.name,
            value=parameter_row.value,
            value_min=parameter_row.value_min,
            value_typ=parameter_row.value_typ,
            value_max=parameter_row.value_max,
            unit=parameter_row.unit,
            condition=dict(parameter_row.condition or {}),
            source_id=parameter_row.source_id,
            page=parameter_row.page,
            method=ExtractionMethod(parameter_row.method) if parameter_row.method else None,
            confidence=float(parameter_row.confidence or 0.0),
            status=ValueStatus(parameter_row.status),
            reasons=reasons,
            raw_text=parameter_row.raw_text,
            created_at=parse_timestamp(parameter_row.created_at),
        )

    def apply_review(self, param_id: str, decision: ReviewDecision) -> ReviewResponse:
        """Accept, correct or reject one reviewed value.

        * ``accept``  -> ``status=accepted``, ``method=manual``, ``confidence=1.0``
        * ``correct`` -> the corrected values are written,
          ``status=accepted``, ``method=manual``, ``confidence=1.0``
        * ``reject``  -> ``status=rejected``

        Every decision is written to the ``review_corrections`` table so that
        the corrections can be fed back into the name map and the prompts.
        """
        with self._scope() as session:
            row = session.get(ParameterRow, param_id)
            if row is None:
                raise KeyError(param_id)
            part_row = session.get(PartRow, row.part_id)
            old_value = row.value
            action = decision.action
            if action == "accept":
                row.status = ValueStatus.ACCEPTED.value
                row.method = ExtractionMethod.MANUAL.value
                row.confidence = 1.0
            elif action == "correct":
                if decision.value is not None:
                    row.value = decision.value
                if decision.value_min is not None:
                    row.value_min = decision.value_min
                if decision.value_typ is not None:
                    row.value_typ = decision.value_typ
                if decision.value_max is not None:
                    row.value_max = decision.value_max
                if decision.unit is not None:
                    row.unit = decision.unit
                if decision.condition:
                    row.condition = dict(decision.condition)
                row.status = ValueStatus.ACCEPTED.value
                row.method = ExtractionMethod.MANUAL.value
                row.confidence = 1.0
            else:  # reject
                row.status = ValueStatus.REJECTED.value
            row.updated_at = utcnow_iso()
            session.add(
                ReviewCorrectionRow(
                    correction_id=_new_id(),
                    param_id=param_id,
                    part_id=row.part_id,
                    action=action,
                    old_value=old_value,
                    new_value=row.value,
                    note=decision.note,
                )
            )
            session.flush()
            item = self._review_item(row, part_row) if part_row is not None else None
            status = ValueStatus(row.status)
        message = {
            "accept": "the value was accepted",
            "correct": "the value was corrected",
            "reject": "the value was rejected",
        }[action]
        return ReviewResponse(
            param_id=param_id,
            status=status,
            message=message,
            item=item,
        )

    # ------------------------------------------------------------------
    # llm accounting
    # ------------------------------------------------------------------
    def record_llm_call(self, record: LLMCallRecord) -> None:
        """Store one LLM call for the cost accounting (NFR-05)."""
        with self._scope() as session:
            session.add(
                LLMCallRow(
                    call_id=record.call_id or _new_id(),
                    chain=record.chain,
                    model=record.model,
                    tokens_in=int(record.tokens_in or 0),
                    tokens_out=int(record.tokens_out or 0),
                    cost=float(record.cost or 0.0),
                    prompt_version=record.prompt_version or "",
                    part_id=record.part_id,
                    cached=1 if record.cached else 0,
                    duration_ms=record.duration_ms,
                    created_at=_dt(record.created_at) or utcnow_iso(),
                )
            )
            session.flush()

    # ------------------------------------------------------------------
    # statistics
    # ------------------------------------------------------------------
    def stats(self) -> StatsResponse:
        """Return the dashboard numbers.

        * ``coverage_pct`` - share of parts that have at least **one**
          accepted value (0 - 100).
        * ``mean_confidence`` - the average confidence of all stored values.
        * ``avg_cost_per_datasheet`` - total LLM cost divided by the number of
          distinct PDF sources (0 when there is no PDF).
        """
        with self._scope() as session:
            parts_total = int(session.scalar(select(func.count()).select_from(PartRow)) or 0)
            parts_by_family = _count_by(session, PartRow.family)
            parts_by_lifecycle = _count_by(session, PartRow.lifecycle_status)
            parts_by_manufacturer = _count_by(session, PartRow.manufacturer)
            parameters_total = int(
                session.scalar(select(func.count()).select_from(ParameterRow)) or 0
            )
            values_by_status = _count_by(session, ParameterRow.status)
            values_by_method = _count_by(session, ParameterRow.method)
            review_pending = int(
                session.scalar(
                    select(func.count())
                    .select_from(ParameterRow)
                    .where(ParameterRow.status == ValueStatus.REVIEW.value)
                )
                or 0
            )
            sources_total = int(session.scalar(select(func.count()).select_from(SourceRow)) or 0)
            parts_with_values = int(
                session.scalar(
                    select(func.count())
                    .select_from(PartRow)
                    .where(
                        select(1)
                        .where(
                            ParameterRow.part_id == PartRow.part_id,
                            ParameterRow.status == ValueStatus.ACCEPTED.value,
                        )
                        .exists()
                    )
                )
                or 0
            )
            mean_confidence = float(
                session.scalar(select(func.avg(ParameterRow.confidence))) or 0.0
            )
            llm_calls_total = int(session.scalar(select(func.count()).select_from(LLMCallRow)) or 0)
            llm_tokens_in = int(
                session.scalar(select(func.coalesce(func.sum(LLMCallRow.tokens_in), 0))) or 0
            )
            llm_tokens_out = int(
                session.scalar(select(func.coalesce(func.sum(LLMCallRow.tokens_out), 0))) or 0
            )
            llm_cost_total = float(
                session.scalar(select(func.coalesce(func.sum(LLMCallRow.cost), 0.0))) or 0.0
            )
            pdf_sources = int(
                session.scalar(
                    select(func.count())
                    .select_from(SourceRow)
                    .where(SourceRow.type == SourceType.PDF.value)
                )
                or 0
            )
        coverage_pct = round(100.0 * parts_with_values / parts_total, 2) if parts_total else 0.0
        avg_cost_per_datasheet = round(llm_cost_total / pdf_sources, 6) if pdf_sources else 0.0
        return StatsResponse(
            parts_total=parts_total,
            parts_by_family=parts_by_family,
            parts_by_lifecycle=parts_by_lifecycle,
            parts_by_manufacturer=parts_by_manufacturer,
            parameters_total=parameters_total,
            values_by_status=values_by_status,
            values_by_method=values_by_method,
            review_pending=review_pending,
            sources_total=sources_total,
            coverage_pct=coverage_pct,
            mean_confidence=round(mean_confidence, 6),
            llm_calls_total=llm_calls_total,
            llm_tokens_in=llm_tokens_in,
            llm_tokens_out=llm_tokens_out,
            llm_cost_total=round(llm_cost_total, 6),
            avg_cost_per_datasheet=avg_cost_per_datasheet,
            generated_at=datetime.now(UTC),
        )


def _count_by(session: Session, column: Any) -> dict[str, int]:
    rows = session.execute(select(column, func.count()).group_by(column)).all()
    return {str(key): int(value) for key, value in rows if key is not None}


def _representative(
    value: float | None,
    value_typ: float | None,
    value_max: float | None,
    value_min: float | None,
) -> float | None:
    """Return the value used for comparisons: typical > value > max > min."""
    for candidate in (value_typ, value, value_max, value_min):
        if candidate is not None:
            return float(candidate)
    return None


class NameMapRepository:
    """Persistence for the ``name_map`` table.

    The tier-1 agent (B) uses it to map a raw table header to a standard
    parameter name, the LLM name mapper (C) proposes new entries and the
    review service (F) approves them.
    """

    def __init__(self, engine_or_session: Engine | Session) -> None:
        self._engine: Engine | None = None
        self._external_session: Session | None = None
        if isinstance(engine_or_session, Session):
            self._external_session = engine_or_session
        else:
            self._engine = engine_or_session

    @contextmanager
    def _scope(self) -> Iterable[Session]:
        if self._external_session is not None:
            yield self._external_session
            return
        if self._engine is None:  # pragma: no cover - defensive
            raise RuntimeError("the repository has neither an engine nor a session")
        session = make_session_factory(self._engine)()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _family_clause(family: str | None):
        return NameMapRow.family.is_(None) if family is None else NameMapRow.family == family

    def lookup(self, raw_name: str, family: str | None = None) -> str | None:
        """Return the standard name of ``raw_name`` or ``None``.

        An approved mapping always wins over an unapproved one.  A mapping of
        the given family wins over a global mapping (``family IS NULL``).
        """
        with self._scope() as session:
            rows = session.scalars(
                select(NameMapRow)
                .where(
                    NameMapRow.raw_name == raw_name,
                    or_(
                        NameMapRow.family == family,
                        NameMapRow.family.is_(None),
                    ),
                )
                .order_by(
                    # family specific first, then approved, then the newest
                    case((NameMapRow.family.is_(None), 1), else_=0),
                    case((NameMapRow.approved == "yes", 0), else_=1),
                    NameMapRow.id.desc(),
                )
            ).all()
            for row in rows:
                if family is not None and row.family == family:
                    return row.standard_name
            for row in rows:
                if row.family is None:
                    return row.standard_name
            return rows[0].standard_name if rows else None

    def add(
        self,
        raw_name: str,
        standard_name: str,
        family: str | None = None,
        approved: bool | str = False,
    ) -> dict[str, Any]:
        """Insert or update one mapping and return it as a dictionary."""
        if isinstance(approved, str):
            approved_value = "yes" if approved.lower() in {"yes", "true", "1"} else "no"
        else:
            approved_value = "yes" if approved else "no"
        with self._scope() as session:
            row = session.scalars(
                select(NameMapRow)
                .where(
                    NameMapRow.raw_name == raw_name,
                    self._family_clause(family),
                )
                .limit(1)
            ).first()
            if row is None:
                row = NameMapRow(
                    raw_name=raw_name,
                    standard_name=standard_name,
                    family=family,
                    approved=approved_value,
                )
                session.add(row)
            else:
                row.standard_name = standard_name
                row.approved = approved_value
            session.flush()
            return self._row_to_dict(row)

    def all_mappings(self, family: str | None = None) -> list[dict[str, Any]]:
        """Return every mapping, optionally filtered by family."""
        with self._scope() as session:
            query = select(NameMapRow).order_by(NameMapRow.raw_name, NameMapRow.id)
            if family is not None:
                query = query.where(NameMapRow.family == family)
            rows = session.scalars(query).all()
            return [self._row_to_dict(row) for row in rows]

    def set_approved(self, raw_name: str, approved: bool | str = True) -> int:
        """Approve (or un-approve) a mapping.  Returns the number of rows changed."""
        if isinstance(approved, str):
            approved_value = "yes" if approved.lower() in {"yes", "true", "1"} else "no"
        else:
            approved_value = "yes" if approved else "no"
        with self._scope() as session:
            rows = session.scalars(select(NameMapRow).where(NameMapRow.raw_name == raw_name)).all()
            for row in rows:
                row.approved = approved_value
            session.flush()
            return len(rows)

    def remove(self, raw_name: str, family: str | None = None) -> int:
        """Delete a mapping.  Returns the number of rows deleted."""
        with self._scope() as session:
            rows = session.scalars(
                select(NameMapRow).where(
                    NameMapRow.raw_name == raw_name,
                    self._family_clause(family),
                )
            ).all()
            for row in rows:
                session.delete(row)
            session.flush()
            return len(rows)

    @staticmethod
    def _row_to_dict(row: NameMapRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "raw_name": row.raw_name,
            "standard_name": row.standard_name,
            "family": row.family,
            "approved": row.approved,
            "created_at": parse_timestamp(row.created_at),
        }

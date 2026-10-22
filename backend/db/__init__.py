"""PartPilot data layer (agent E-data).

The package implements the frozen ``PartsRepository`` protocol of
``shared.interfaces`` on top of SQLAlchemy and the reference schema
``shared/db_schema.sql``.

Typical use::

    from db import SqlAlchemyPartsRepository, init_db
    from db.session import create_engine_from_settings

    engine = create_engine_from_settings()
    init_db(engine)
    repo = SqlAlchemyPartsRepository(engine)
    rows, total = repo.list_parts()

Public API
----------
``SqlAlchemyPartsRepository``
    The repository of ``shared.interfaces.PartsRepository``.
``NameMapRepository``
    The raw-name -> standard-name table.
``create_engine_for_url`` / ``create_engine_from_settings`` / ``create_memory_engine``
    Engines.
``session_scope`` / ``init_db`` / ``migrate``
    Sessions and schema management.
``load_seed``
    The idempotent seed loader (``python -m db.seed``).
"""

from __future__ import annotations

from typing import Any

from db.models import Base
from db.repository import KEY_PARAMETERS, NameMapRepository, SqlAlchemyPartsRepository
from db.session import (
    create_engine_for_url,
    create_engine_from_settings,
    create_memory_engine,
    init_db,
    migrate,
    session_scope,
)


def __getattr__(name: str) -> Any:
    """Import the seed loader lazily.

    ``db.seed`` has to stay lazy: ``python -m db.seed`` would otherwise
    import the module twice (once through this package, once through
    ``runpy``) and Python would warn about it.
    """
    if name == "load_seed":
        from db.seed import load_seed

        return load_seed
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Base",
    "KEY_PARAMETERS",
    "NameMapRepository",
    "SqlAlchemyPartsRepository",
    "create_engine_for_url",
    "create_engine_from_settings",
    "create_memory_engine",
    "init_db",
    "load_seed",
    "migrate",
    "session_scope",
]

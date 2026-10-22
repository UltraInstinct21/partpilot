"""Engine, session and schema management for PartPilot (agent E-data).

Public API
----------
``create_engine_for_url(url)``
    Build a SQLAlchemy engine for ``url``.  For SQLite the foreign key
    pragma is switched on (the reference schema relies on it).
``create_engine_from_settings()``
    Build the engine for ``Settings.database_url``.
``create_memory_engine()``
    Build an in-memory SQLite engine that keeps **one** connection alive
    (``StaticPool``) so that every session sees the same database.  Used by
    the test suite.
``sessionmaker`` / ``session_scope()``
    The unit of work.
``init_db(engine)``
    Create the schema.
``migrate(engine)``
    Apply the numbered SQL migrations in ``backend/db/migrations``.

Migration approach
------------------
The project uses **ordered, numbered SQL files** instead of alembic:

* every file in ``backend/db/migrations`` is applied exactly once, in lexical
  order, inside one transaction;
* applied versions are recorded in the ``schema_migrations`` table together
  with a checksum of the file;
* a migration file therefore has to be edited in a *new* file, never in an
  applied one.

Why not alembic: the schema of this project is a single, frozen DDL file
(``backend/shared/db_schema.sql``) that is owned by the orchestrator.  Plain
SQL keeps the migration history readable, has no Python import path
dependencies and cannot drift away from the reference schema.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base

__all__ = [
    "MIGRATIONS_DIR",
    "SCHEMA_FILE",
    "apply_reference_schema",
    "create_engine_for_url",
    "create_engine_from_settings",
    "create_memory_engine",
    "init_db",
    "migrate",
    "migration_files",
    "parse_timestamp",
    "session_scope",
    "split_sql_statements",
]

#: ``backend/db/session.py`` -> ``backend/db`` -> ``backend``
BACKEND_DIR = Path(__file__).resolve().parents[1]
#: the frozen reference schema (owned by the orchestrator).
SCHEMA_FILE = BACKEND_DIR / "shared" / "db_schema.sql"
#: the ordered SQL migrations owned by this agent.
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    checksum   TEXT NOT NULL DEFAULT ''
)
"""


# --------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def create_engine_for_url(url: str, *, echo: bool = False, **kwargs: Any) -> Engine:
    """Return a SQLAlchemy engine for ``url``.

    For SQLite the ``foreign_keys`` pragma is enabled on every connection -
    SQLite disables foreign keys by default, and the reference schema relies
    on ``ON DELETE CASCADE`` / ``ON DELETE SET NULL``.
    """
    connect_args: dict[str, Any] = dict(kwargs.pop("connect_args", {}) or {})
    if _is_sqlite(url):
        connect_args.setdefault("check_same_thread", False)
        if url.startswith("sqlite:///"):
            # a file backed database: make sure the directory exists
            raw = url[len("sqlite:///") :]
            if raw and raw != ":memory:":
                Path(raw).expanduser().parent.mkdir(parents=True, exist_ok=True)
    kwargs.setdefault("future", True)
    engine = create_engine(url, echo=echo, connect_args=connect_args, **kwargs)
    if _is_sqlite(url):
        _register_sqlite_pragma(engine)
    return engine


def _register_sqlite_pragma(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection: Any, _connection_record: Any) -> None:  # pragma: no cover
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def create_engine_from_settings(*, echo: bool | None = None) -> Engine:
    """Return the engine for ``Settings.database_url``."""
    from shared.config import get_settings

    settings = get_settings()
    return create_engine_for_url(
        settings.database_url,
        echo=settings.sql_echo if echo is None else echo,
    )


def create_memory_engine(*, echo: bool = False) -> Engine:
    """Return an in-memory SQLite engine that shares one connection."""
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        echo=echo,
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _register_sqlite_pragma(engine)
    return engine


# --------------------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------------------


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a ``sessionmaker`` bound to ``engine``."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Context manager that yields a session and commits on success."""
    if engine is None:
        engine = create_engine_from_settings()
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# --------------------------------------------------------------------------------------
# SQL helpers
# --------------------------------------------------------------------------------------


def split_sql_statements(script: str) -> list[str]:
    """Split a SQL script into single statements.

    ``--`` line comments are removed, single quoted strings are respected.
    """
    statements: list[str] = []
    buffer: list[str] = []
    index = 0
    length = len(script)
    in_string = False
    while index < length:
        char = script[index]
        if in_string:
            buffer.append(char)
            if char == "'":
                if index + 1 < length and script[index + 1] == "'":
                    buffer.append("'")
                    index += 2
                    continue
                in_string = False
            index += 1
            continue
        if char == "'":
            in_string = True
            buffer.append(char)
            index += 1
            continue
        if char == "-" and script[index : index + 2] == "--":
            newline = script.find("\n", index)
            if newline == -1:
                break
            index = newline + 1
            continue
        if char == ";":
            statements.append("".join(buffer))
            buffer = []
            index += 1
            continue
        buffer.append(char)
        index += 1
    statements.append("".join(buffer))
    return [statement.strip() for statement in statements if statement.strip()]


def apply_reference_schema(engine: Engine, schema_file: Path | None = None) -> None:
    """Execute the frozen reference schema ``backend/shared/db_schema.sql``.

    The file uses ``CREATE TABLE IF NOT EXISTS`` everywhere, so calling it
    repeatedly is safe and never destroys data.
    """
    path = schema_file or SCHEMA_FILE
    script = path.read_text(encoding="utf-8")
    with engine.begin() as connection:
        for statement in split_sql_statements(script):
            connection.exec_driver_sql(statement)


# --------------------------------------------------------------------------------------
# Migrations
# --------------------------------------------------------------------------------------


def migration_files(directory: Path | None = None) -> list[Path]:
    """Return the migration files in the order they have to be applied."""
    folder = directory or MIGRATIONS_DIR
    if not folder.exists():
        return []
    return sorted(folder.glob("*.sql"), key=lambda path: path.name)


def migrate(engine: Engine, directory: Path | None = None) -> list[str]:
    """Apply every pending migration and return the applied versions."""
    applied: list[str] = []
    with engine.begin() as connection:
        connection.exec_driver_sql(_SCHEMA_MIGRATIONS_DDL)
        rows = connection.exec_driver_sql("SELECT version FROM schema_migrations")
        known = {row[0] for row in rows}
        for path in migration_files(directory):
            version = path.name
            if version in known:
                continue
            script = path.read_text(encoding="utf-8")
            for statement in split_sql_statements(script):
                connection.exec_driver_sql(statement)
            checksum = hashlib.sha256(script.encode("utf-8")).hexdigest()
            connection.exec_driver_sql(
                "INSERT INTO schema_migrations (version, checksum) VALUES (?, ?)",
                (version, checksum),
            )
            known.add(version)
            applied.append(version)
    return applied


def init_db(engine: Engine | None = None, *, schema_file: Path | None = None) -> Engine:
    """Create the schema and return the engine.

    The order matters:

    1. the frozen reference schema is executed first, so the tables carry the
       exact CHECK constraints and indexes of the contract;
    2. the numbered migrations run afterwards (they are idempotent);
    3. ``metadata.create_all(checkfirst=True)`` is the safety net for a table
       that only exists in the ORM - it never touches an existing table, so it
       cannot remove a CHECK constraint.
    """
    if engine is None:
        engine = create_engine_from_settings()
    apply_reference_schema(engine, schema_file=schema_file)
    migrate(engine)
    Base.metadata.create_all(engine, checkfirst=True)
    return engine


# --------------------------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------------------------


def parse_timestamp(value: str | None) -> datetime | None:
    """Parse a timestamp that was written by the ORM or by SQLite.

    Both formats are supported: ISO-8601 (``2026-01-01T12:00:00+00:00``) and
    the SQLite ``datetime('now')`` format (``2026-01-01 12:00:00``).
    """
    if value is None or value == "":
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed

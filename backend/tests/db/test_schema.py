"""The created schema must be exactly the frozen reference schema."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect

from db.models import Base
from db.session import SCHEMA_FILE, init_db, migrate, split_sql_statements

EXPECTED_TABLES = {
    "parts",
    "parameters",
    "sources",
    "offers",
    "name_map",
    "llm_calls",
    "review_corrections",
}


def _schema_objects(connection) -> set[tuple[str, str, str]]:
    rows = connection.exec_driver_sql(
        "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {(row[0], row[1], (row[2] or "").strip()) for row in rows}


def test_reference_schema_file_exists() -> None:
    assert SCHEMA_FILE.exists()
    assert SCHEMA_FILE.name == "db_schema.sql"


def test_tables_match_the_reference_schema(engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names()) - {"schema_migrations"}
    assert tables == EXPECTED_TABLES


def test_columns_match_the_reference_schema(engine, tmp_path: Path) -> None:
    """The ORM and the reference DDL have to describe the same columns."""
    from sqlalchemy import create_engine

    reference = create_engine(f"sqlite:///{tmp_path / 'reference.db'}")
    with reference.begin() as connection:
        script = SCHEMA_FILE.read_text(encoding="utf-8")
        for statement in split_sql_statements(script):
            connection.exec_driver_sql(statement)

    left = inspect(reference)
    right = inspect(engine)
    for table in sorted(EXPECTED_TABLES):
        left_columns = {column["name"]: str(column["type"]) for column in left.get_columns(table)}
        right_columns = {column["name"]: str(column["type"]) for column in right.get_columns(table)}
        assert left_columns == right_columns, f"{table} differs from the reference schema"


def test_indexes_match_the_reference_schema(engine, tmp_path: Path) -> None:
    from sqlalchemy import create_engine

    reference = create_engine(f"sqlite:///{tmp_path / 'reference.db'}")
    with reference.begin() as connection:
        script = SCHEMA_FILE.read_text(encoding="utf-8")
        for statement in split_sql_statements(script):
            connection.exec_driver_sql(statement)

    def index_names(inspector, table: str) -> set[str]:
        return {index["name"] for index in inspector.get_indexes(table)}

    left = inspect(reference)
    right = inspect(engine)
    for table in sorted(EXPECTED_TABLES):
        assert index_names(left, table) == index_names(right, table), f"{table} indexes differ"


def test_check_constraints_are_enforced(engine) -> None:
    """A value with an illegal status must be refused by the database."""
    import sqlalchemy as sa

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO parts (part_id, mpn, manufacturer, family) "
            "VALUES ('p1', 'X', 'Y', 'mosfet')"
        )
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO parameters (param_id, part_id, name, status) "
                "VALUES ('x1', 'p1', 'vds_max', 'bogus')"
            )


def test_foreign_keys_are_enabled(engine) -> None:
    import sqlalchemy as sa

    with engine.begin() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO parameters (param_id, part_id, name) VALUES ('x2', 'nope', 'vds_max')"
            )


def test_migrations_are_recorded_and_applied_once(engine) -> None:
    applied = migrate(engine)
    assert applied == []  # already applied by init_db
    with engine.connect() as connection:
        versions = [
            row[0] for row in connection.exec_driver_sql("SELECT version FROM schema_migrations")
        ]
    assert "0001_initial.sql" in versions


def test_orm_metadata_has_no_table_without_ddl() -> None:
    """The ORM knows exactly the tables of the reference schema."""
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_init_db_is_idempotent(engine) -> None:
    init_db(engine)
    init_db(engine)
    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert EXPECTED_TABLES.issubset(tables)

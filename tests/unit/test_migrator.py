from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.database.migrator import (
    MigrationChecksumError,
    MigrationError,
    PendingMigrationsError,
    UnknownAppliedMigrationError,
    apply_migrations,
    discover_migrations,
    split_sql_statements,
    verify_migrations,
)


def test_repository_migrations_are_sequential_and_checksummed():
    migrations = discover_migrations()
    assert [item.version for item in migrations] == [1, 2, 3, 4]
    assert all(len(item.checksum) == 64 for item in migrations)


def test_discovery_rejects_duplicate_versions(tmp_path: Path):
    (tmp_path / "0001_first.sql").write_text("SELECT 1;")
    (tmp_path / "0001_second.sql").write_text("SELECT 2;")
    with pytest.raises(MigrationError):
        discover_migrations(tmp_path)


def test_discovery_rejects_unversioned_sql_file(tmp_path: Path):
    (tmp_path / "initial.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError):
        discover_migrations(tmp_path)


def test_sql_splitter_keeps_comments_with_following_statement():
    statements = split_sql_statements("-- comment\nCREATE TABLE x (id INTEGER);\nCREATE INDEX ix_x ON x(id);")
    assert len(statements) == 2
    assert statements[0].startswith("-- comment")


def make_ledger(engine, rows):
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, filename TEXT NOT NULL, checksum TEXT NOT NULL)"
        )
        for version, filename, checksum in rows:
            connection.execute(
                text(
                    "INSERT INTO schema_migrations (version, filename, checksum) "
                    "VALUES (:version, :filename, :checksum)"
                ),
                {"version": version, "filename": filename, "checksum": checksum},
            )


def test_verify_migrations_fails_closed_when_ledger_is_missing():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with pytest.raises(PendingMigrationsError):
            verify_migrations(engine)
    finally:
        engine.dispose()


def test_verify_migrations_accepts_exact_applied_set():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        migrations = discover_migrations()
        make_ledger(
            engine,
            [(item.version, item.filename, item.checksum) for item in migrations],
        )
        result = verify_migrations(engine)
        assert result == {"ok": True, "current_version": 4}
    finally:
        engine.dispose()


def test_verify_migrations_detects_modified_applied_file():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        migrations = discover_migrations()
        make_ledger(
            engine,
            [
                (
                    item.version,
                    item.filename,
                    "0" * 64 if item.version == 2 else item.checksum,
                )
                for item in migrations
            ],
        )
        with pytest.raises(MigrationChecksumError):
            verify_migrations(engine)
    finally:
        engine.dispose()


def test_verify_migrations_detects_unknown_database_version():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        migrations = discover_migrations()
        make_ledger(
            engine,
            [(item.version, item.filename, item.checksum) for item in migrations]
            + [(99, "0099_future.sql", "f" * 64)],
        )
        with pytest.raises(UnknownAppliedMigrationError):
            verify_migrations(engine)
    finally:
        engine.dispose()


def test_apply_migrations_refuses_non_postgresql_database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with pytest.raises(MigrationError, match="only on PostgreSQL"):
            apply_migrations(engine)
    finally:
        engine.dispose()

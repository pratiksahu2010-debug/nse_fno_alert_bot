"""Checksummed, serialized PostgreSQL schema migration runner."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


MIGRATION_NAME = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")
ADVISORY_LOCK_KEY = 7319248206101


class MigrationError(RuntimeError):
    """Base class for migration failures."""


class PendingMigrationsError(MigrationError):
    """The database schema is behind the application migration set."""


class MigrationChecksumError(MigrationError):
    """An already-applied migration file has been changed."""


class UnknownAppliedMigrationError(MigrationError):
    """The database records a migration absent from this code version."""


@dataclass(frozen=True)
class Migration:
    version: int
    filename: str
    checksum: str
    sql: str


def discover_migrations(directory: str | Path | None = None) -> list[Migration]:
    root = Path(directory) if directory is not None else Path(__file__).with_name("migrations")
    migrations = []
    seen = set()
    for path in sorted(root.glob("*.sql")):
        match = MIGRATION_NAME.match(path.name)
        if match is None:
            raise MigrationError(f"invalid migration filename: {path.name}")
        version = int(match.group("version"))
        if version in seen:
            raise MigrationError(f"duplicate migration version: {version}")
        seen.add(version)
        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=version,
                filename=path.name,
                checksum=sha256(sql.encode("utf-8")).hexdigest(),
                sql=sql,
            )
        )
    if not migrations:
        raise MigrationError(f"no SQL migrations found in {root}")
    return migrations


def split_sql_statements(sql: str) -> list[str]:
    """Split the project's simple DDL scripts; procedural SQL blocks are unsupported."""
    # Protect semicolons inside full-line SQL comments without discarding
    # comments or detaching them from the statement that follows.
    marker = "__SQL_COMMENT_SEMICOLON__"
    protected = re.sub(
        r"(?m)^([ \t]*--[^\n]*)",
        lambda match: match.group(1).replace(";", marker),
        sql,
    )
    return [
        part.strip().replace(marker, ";")
        for part in protected.split(";")
        if part.strip()
    ]


def apply_migrations(engine, directory: str | Path | None = None) -> dict:
    """Apply pending migrations atomically under a PostgreSQL advisory lock.

    This function is an explicit administrative operation. Application startup
    calls verify_migrations only; it never mutates the database schema.
    """
    if engine.dialect.name != "postgresql":
        raise MigrationError("schema migrations are supported only on PostgreSQL")
    migrations = discover_migrations(directory)

    with engine.begin() as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": ADVISORY_LOCK_KEY},
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                filename VARCHAR(200) NOT NULL,
                checksum VARCHAR(64) NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        applied = connection.execute(
            text("SELECT version, filename, checksum FROM schema_migrations")
        ).mappings().all()
        known_versions = {migration.version for migration in migrations}
        unknown = [row["version"] for row in applied if row["version"] not in known_versions]
        if unknown:
            raise UnknownAppliedMigrationError(
                f"database contains migration versions unknown to this code: {unknown}"
            )
        applied_by_version = {row["version"]: row for row in applied}
        newly_applied = []

        for migration in migrations:
            existing = applied_by_version.get(migration.version)
            if existing is not None:
                if (
                    existing["filename"] != migration.filename
                    or existing["checksum"] != migration.checksum
                ):
                    raise MigrationChecksumError(
                        f"applied migration {migration.filename} differs from its recorded checksum"
                    )
                continue

            for statement in split_sql_statements(migration.sql):
                connection.exec_driver_sql(statement)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations (version, filename, checksum) "
                    "VALUES (:version, :filename, :checksum)"
                ),
                {
                    "version": migration.version,
                    "filename": migration.filename,
                    "checksum": migration.checksum,
                },
            )
            newly_applied.append(migration.version)

    return {
        "ok": True,
        "newly_applied": newly_applied,
        "current_version": migrations[-1].version,
    }


def verify_migrations(engine, directory: str | Path | None = None) -> dict:
    """Read-only startup gate: fail closed if any migration is missing or changed."""
    migrations = discover_migrations(directory)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT version, filename, checksum FROM schema_migrations")
            ).mappings().all()
    except SQLAlchemyError as exc:
        raise PendingMigrationsError(
            "schema_migrations is missing or unreadable; run python -m scripts.migrate"
        ) from exc

    applied_by_version = {row["version"]: row for row in rows}
    known_versions = {migration.version for migration in migrations}
    unknown = [version for version in applied_by_version if version not in known_versions]
    if unknown:
        raise UnknownAppliedMigrationError(
            f"database contains migration versions unknown to this code: {unknown}"
        )

    pending = []
    for migration in migrations:
        applied = applied_by_version.get(migration.version)
        if applied is None:
            pending.append(migration.version)
            continue
        if (
            applied["filename"] != migration.filename
            or applied["checksum"] != migration.checksum
        ):
            raise MigrationChecksumError(
                f"applied migration {migration.filename} differs from its recorded checksum"
            )
    if pending:
        raise PendingMigrationsError(
            f"database is missing migrations {pending}; run python -m scripts.migrate"
        )
    return {"ok": True, "current_version": migrations[-1].version}

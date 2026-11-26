"""Explicit database migration command: python -m scripts.migrate."""
from app.config import Settings
from app.database.connection import make_engine
from app.database.migrator import apply_migrations


def main():
    settings = Settings()
    engine = make_engine(settings.database_url)
    try:
        result = apply_migrations(engine)
        print(result)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

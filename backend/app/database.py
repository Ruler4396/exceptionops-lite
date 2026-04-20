from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATA_DIR, settings


DATA_DIR.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_runtime_migrations()


def _apply_runtime_migrations() -> None:
    inspector = inspect(engine)
    if "cases" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("cases")}
    statements = {
        "owner": "ALTER TABLE cases ADD COLUMN owner VARCHAR(128) DEFAULT ''",
        "assigned_at": "ALTER TABLE cases ADD COLUMN assigned_at DATETIME",
        "due_at": "ALTER TABLE cases ADD COLUMN due_at DATETIME",
    }
    with engine.begin() as connection:
        for column_name, statement in statements.items():
            if column_name not in columns:
                connection.execute(text(statement))
        connection.execute(text("UPDATE cases SET owner = '' WHERE owner IS NULL"))

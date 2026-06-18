"""SQLAlchemy engine/session helpers."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from agentfabric.server.config import Settings

Base = declarative_base()


def create_engine_from_settings(settings: Settings):
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, future=True, pool_pre_ping=True, connect_args=connect_args)


def build_session_factory(settings: Settings):
    engine = create_engine_from_settings(settings)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session), engine


def run_migrations(database_url: str, *, alembic_ini_path: str = "alembic.ini") -> None:
    ini_path = Path(alembic_ini_path)
    if not ini_path.exists():
        raise FileNotFoundError(f"alembic config not found: {alembic_ini_path}")
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


@contextmanager
def session_scope(session_factory) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

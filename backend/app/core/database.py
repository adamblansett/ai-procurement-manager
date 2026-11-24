from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.core.config import Settings


class Base(DeclarativeBase):
    """Declarative base for all async SQLAlchemy ORM models."""


def create_engine_and_sessionmaker(
    database_url: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Build an async SQLAlchemy engine and session factory tailored to the backend URL."""
    engine_kwargs: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            engine_kwargs["poolclass"] = StaticPool
    else:
        engine_kwargs["pool_pre_ping"] = True

    engine = create_async_engine(database_url, **engine_kwargs)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, session_factory


def register_models() -> None:
    """Import all domain model modules so SQLAlchemy metadata contains every table."""
    import app.benchmarks.models  # noqa: F401
    import app.contracts.models  # noqa: F401
    import app.core.models  # noqa: F401
    import app.purchasing.models  # noqa: F401
    import app.renewals.models  # noqa: F401


async def init_db(engine: AsyncEngine) -> None:
    """Create database tables idempotently during startup or test initialization."""
    register_models()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def check_db_ready(engine: AsyncEngine) -> bool:
    """Execute a lightweight connectivity probe against the configured database."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield an async database session scoped to the active HTTP request."""
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session


def get_app_settings(request: Request) -> Settings:
    """Return runtime application settings attached to FastAPI state."""
    settings: Settings = request.app.state.settings
    return settings

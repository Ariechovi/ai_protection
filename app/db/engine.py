from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.base import Base

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine():
    global _engine, _session_factory
    settings = get_settings()
    if not settings.database_url:
        return None
    if _engine is None:
        _engine = create_async_engine(settings.database_url, echo=False)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def init_db() -> None:
    # Ensure SQLAlchemy sees every model before metadata.create_all().
    from app.db import models  # noqa: F401

    engine = _build_engine()
    if engine is None:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    _build_engine()
    if _session_factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.database import init_db
from app.core.seed import seed_demo_data
from app.main import create_app


@pytest_asyncio.fixture
async def app_instance() -> AsyncIterator[FastAPI]:
    """Create an isolated in-memory FastAPI instance per test function."""
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        auto_seed_demo_data=False,
        llm_default_provider="mock",
    )
    application = create_app(settings)
    await init_db(application.state.engine)
    try:
        yield application
    finally:
        await application.state.engine.dispose()


@pytest_asyncio.fixture
async def client(app_instance: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async HTTP test client against an empty initialized database."""
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def seeded_client(app_instance: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async HTTP test client pre-populated with realistic procurement seed data."""
    await seed_demo_data(
        app_instance.state.session_factory,
        app_instance.state.llm_router,
        app_instance.state.settings,
    )
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client

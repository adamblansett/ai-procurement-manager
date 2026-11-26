from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import Settings, get_settings, validate_production_security
from app.core.database import create_engine_and_sessionmaker, init_db
from app.core.llm import LLMRouter
from app.core.middleware import (
    AuthEnforcementMiddleware,
    ObservabilityMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.observability import MetricsRegistry
from app.core.seed import seed_demo_data


def create_app(settings_override: Settings | None = None) -> FastAPI:
    """Construct and configure the FastAPI application."""
    cfg = settings_override or get_settings()
    validate_production_security(cfg)

    engine, session_factory = create_engine_and_sessionmaker(cfg.database_url)
    llm_router = LLMRouter(cfg)
    metrics = MetricsRegistry()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await init_db(engine)
        if cfg.auto_seed_demo_data and cfg.app_env.strip().lower() != "production":
            await seed_demo_data(session_factory, llm_router, cfg)
        try:
            yield
        finally:
            await engine.dispose()

    application = FastAPI(
        title=cfg.app_name,
        version="0.1.0",
        description=(
            "Open-source, self-hosted AI procurement and vendor management platform for "
            "supplier contract comparison, pricing benchmarks, PO validation, and renewal "
            "tracking."
        ),
        lifespan=lifespan,
    )
    application.state.settings = cfg
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.llm_router = llm_router
    application.state.metrics = metrics

    application.add_middleware(AuthEnforcementMiddleware, settings=cfg)
    application.add_middleware(RateLimitMiddleware, settings=cfg)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(SecurityHeadersMiddleware, settings=cfg)
    application.add_middleware(ObservabilityMiddleware, settings=cfg, metrics=metrics)
    application.include_router(api_v1_router, prefix=cfg.api_v1_prefix)
    return application


app = create_app()

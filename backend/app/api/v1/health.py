from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.database import check_db_ready
from app.core.observability import MetricsRegistry

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    app_name: str
    version: str
    environment: str
    llm_provider: str
    database: str = "ok"
    pii_redaction_enabled: bool = True


def _resolve_settings(request: Request) -> Settings:
    settings: Settings | None = getattr(request.app.state, "settings", None)
    return settings or get_settings()


@router.get("", response_model=HealthResponse)
@router.get("/live", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Return service health and runtime configuration summary."""
    settings = _resolve_settings(request)
    return HealthResponse(
        status="ok",
        service=settings.app_slug,
        app_name=settings.app_name,
        version="0.1.0",
        environment=settings.app_env,
        llm_provider=settings.llm_default_provider,
        database="ok",
        pii_redaction_enabled=settings.llm_redact_pii_for_cloud,
    )


@router.get("/ready", response_model=HealthResponse)
async def readiness_check(request: Request) -> HealthResponse:
    """Verify database connectivity before marking the instance ready for traffic."""
    settings = _resolve_settings(request)
    engine = getattr(request.app.state, "engine", None)
    db_ok = True if engine is None else await check_db_ready(engine)
    if not db_ok:
        raise HTTPException(status_code=503, detail="Database readiness check failed")
    return HealthResponse(
        status="ok",
        service=settings.app_slug,
        app_name=settings.app_name,
        version="0.1.0",
        environment=settings.app_env,
        llm_provider=settings.llm_default_provider,
        database="ok",
        pii_redaction_enabled=settings.llm_redact_pii_for_cloud,
    )


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics(request: Request) -> PlainTextResponse:
    """Expose Prometheus-compatible HTTP request and latency metrics."""
    metrics: MetricsRegistry | None = getattr(request.app.state, "metrics", None)
    body = metrics.render_prometheus() if metrics is not None else ""
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/telemetry")
async def telemetry_summary(request: Request) -> dict[str, Any]:
    """Return JSON observability summary and runtime guardrail flags."""
    settings = _resolve_settings(request)
    metrics: MetricsRegistry | None = getattr(request.app.state, "metrics", None)
    summary = metrics.summary() if metrics is not None else {"total_requests": 0}
    return {
        **summary,
        "otel_enabled": settings.otel_enabled,
        "rate_limit_enabled": settings.rate_limit_enabled,
        "auth_required": settings.auth_required,
    }

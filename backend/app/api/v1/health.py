from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.database import check_db_ready

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

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.governance import router as governance_router
from app.api.v1.health import router as health_router
from app.api.v1.vendors import router as vendors_router
from app.benchmarks.router import router as benchmarks_router
from app.contracts.router import router as contracts_router
from app.purchasing.router import router as purchasing_router
from app.renewals.router import router as renewals_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(vendors_router)
api_v1_router.include_router(contracts_router)
api_v1_router.include_router(benchmarks_router)
api_v1_router.include_router(purchasing_router)
api_v1_router.include_router(renewals_router)
api_v1_router.include_router(governance_router)

from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.benchmarks.models import PricingBenchmark
from app.contracts.models import Contract
from app.core.config import Settings
from app.core.database import get_app_settings, get_db
from app.core.llm import LLMRouter, get_llm_router
from app.core.models import ApprovalRequest, AuditLog, Vendor
from app.core.seed import seed_demo_data
from app.purchasing.models import PurchaseOrder
from app.renewals.models import RenewalItem
from app.renewals.schemas import RenewalRead
from app.renewals.service import to_renewal_read

router = APIRouter(tags=["dashboard"])


class CategorySpendItem(BaseModel):
    category: str
    annual_spend: float
    vendor_count: int


class AuditActivitySummary(BaseModel):
    sequence_num: int
    actor: str
    action: str
    entity_type: str
    summary: str
    entry_hash: str
    created_at: datetime


class DashboardSummaryResponse(BaseModel):
    total_vendors: int
    total_annual_spend: float
    active_contracts: int
    high_risk_contracts: int
    avg_contract_risk_score: float
    benchmarks_count: int
    pending_approvals_count: int
    open_pos_count: int
    blocked_pos_count: int
    urgent_renewals_count: int
    estimated_savings_opportunity: float
    spend_by_category: list[CategorySpendItem]
    urgent_renewals: list[RenewalRead]
    recent_audit_logs: list[AuditActivitySummary]


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
) -> DashboardSummaryResponse:
    """Aggregate cross-module procurement KPIs, urgent renewals, and recent audit activity."""
    vendors = list((await db.execute(select(Vendor))).scalars().all())
    contracts = list((await db.execute(select(Contract))).scalars().all())
    benchmarks = list((await db.execute(select(PricingBenchmark))).scalars().all())
    approvals = list(
        (await db.execute(select(ApprovalRequest).where(ApprovalRequest.status == "pending")))
        .scalars()
        .all()
    )
    pos = list((await db.execute(select(PurchaseOrder))).scalars().all())
    renewals = list(
        (await db.execute(select(RenewalItem).order_by(RenewalItem.notice_deadline.asc())))
        .scalars()
        .all()
    )
    recent_logs = list(
        (await db.execute(select(AuditLog).order_by(AuditLog.sequence_num.desc()).limit(8)))
        .scalars()
        .all()
    )

    vendor_names = {v.id: v.name for v in vendors}
    total_annual_spend = round(sum(v.annual_spend for v in vendors), 2)

    cat_spend: dict[str, float] = defaultdict(float)
    cat_count: dict[str, int] = defaultdict(int)
    for v in vendors:
        cat_spend[v.category] += v.annual_spend
        cat_count[v.category] += 1
    spend_by_category = sorted(
        [
            CategorySpendItem(
                category=cat,
                annual_spend=round(amount, 2),
                vendor_count=cat_count[cat],
            )
            for cat, amount in cat_spend.items()
        ],
        key=lambda item: item.annual_spend,
        reverse=True,
    )

    high_risk_contracts = sum(1 for c in contracts if c.risk_level in {"high", "critical"})
    avg_contract_risk = (
        round(sum(c.risk_score for c in contracts) / len(contracts), 1) if contracts else 0.0
    )

    open_pos_count = sum(1 for p in pos if p.status in {"draft", "validated", "pending_approval"})
    blocked_pos_count = sum(1 for p in pos if p.status == "blocked")

    renewal_reads = [to_renewal_read(r, vendor_names.get(r.vendor_id, "")) for r in renewals]
    urgent_renewals = [r for r in renewal_reads if r.urgency in {"overdue", "critical", "upcoming"}]

    savings_total = 0.0
    for r in renewals:
        brief_savings = (
            r.brief_data_json.get("estimated_annual_savings") if r.brief_data_json else None
        )
        if isinstance(brief_savings, int | float):
            savings_total += float(brief_savings)
        elif r.proposed_uplift_pct > 3.0:
            # Estimate conservative uplift avoidance down to 3.0% ceiling when brief not yet run.
            avoided_pct = max(0.0, r.proposed_uplift_pct - 3.0)
            savings_total += r.current_annual_value * (avoided_pct / 100.0)

    return DashboardSummaryResponse(
        total_vendors=len(vendors),
        total_annual_spend=total_annual_spend,
        active_contracts=len(contracts),
        high_risk_contracts=high_risk_contracts,
        avg_contract_risk_score=avg_contract_risk,
        benchmarks_count=len(benchmarks),
        pending_approvals_count=len(approvals),
        open_pos_count=open_pos_count,
        blocked_pos_count=blocked_pos_count,
        urgent_renewals_count=len(urgent_renewals),
        estimated_savings_opportunity=round(savings_total, 2),
        spend_by_category=spend_by_category,
        urgent_renewals=urgent_renewals[:5],
        recent_audit_logs=[
            AuditActivitySummary(
                sequence_num=log.sequence_num,
                actor=log.actor,
                action=log.action,
                entity_type=log.entity_type,
                summary=log.summary,
                entry_hash=log.entry_hash,
                created_at=log.created_at,
            )
            for log in recent_logs
        ],
    )


@router.post("/seed")
async def trigger_seed(
    request: Request,
    settings: Settings = Depends(get_app_settings),
    llm_router: LLMRouter = Depends(get_llm_router),
) -> dict[str, Any]:
    """Idempotently populate realistic demo procurement data in non-production environments."""
    if settings.app_env.strip().lower() == "production":
        raise HTTPException(
            status_code=403,
            detail="Demo seeding endpoint is disabled in production.",
        )
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return await seed_demo_data(session_factory, llm_router, settings)

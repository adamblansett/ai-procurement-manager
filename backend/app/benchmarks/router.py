from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.benchmarks.models import PricingBenchmark
from app.benchmarks.schemas import (
    BenchmarkSummaryRead,
    PricingBenchmarkCreate,
    PricingBenchmarkRead,
    QuoteAnalyzeRequest,
    QuoteAnalyzeResponse,
)
from app.benchmarks.service import analyze_quote_pricing, get_benchmark_summary
from app.core.database import get_db
from app.core.governance import record_audit_event
from app.core.models import Vendor

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("", response_model=list[PricingBenchmarkRead])
async def list_benchmarks(
    category: str | None = None,
    sku_code: str | None = None,
    vendor_id: str | None = None,
    volume_tier: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[PricingBenchmarkRead]:
    """List normalized historical SKU and SaaS seat pricing benchmarks."""
    stmt = select(PricingBenchmark).order_by(
        PricingBenchmark.effective_year.desc(), PricingBenchmark.quoted_unit_price.asc()
    )
    if category:
        stmt = stmt.where(PricingBenchmark.category == category)
    if sku_code:
        stmt = stmt.where(PricingBenchmark.sku_code == sku_code)
    if vendor_id:
        stmt = stmt.where(PricingBenchmark.vendor_id == vendor_id)
    if volume_tier:
        stmt = stmt.where(PricingBenchmark.volume_tier == volume_tier)

    rows = (await db.execute(stmt)).scalars().all()
    vendor_ids = {r.vendor_id for r in rows if r.vendor_id}
    vendor_names: dict[str, str] = {}
    if vendor_ids:
        vendors = (
            (await db.execute(select(Vendor).where(Vendor.id.in_(vendor_ids)))).scalars().all()
        )
        vendor_names = {v.id: v.name for v in vendors}

    return [
        PricingBenchmarkRead.model_validate(row).model_copy(
            update={"vendor_name": vendor_names.get(row.vendor_id or "", "")}
        )
        for row in rows
    ]


@router.post("", response_model=PricingBenchmarkRead, status_code=status.HTTP_201_CREATED)
async def create_benchmark(
    payload: PricingBenchmarkCreate, db: AsyncSession = Depends(get_db)
) -> PricingBenchmarkRead:
    """Record a normalized vendor quote or executed contract unit price."""
    benchmark = PricingBenchmark(**payload.model_dump())
    db.add(benchmark)
    await db.flush()

    vendor_name = ""
    if benchmark.vendor_id:
        vendor = await db.get(Vendor, benchmark.vendor_id)
        vendor_name = vendor.name if vendor else ""

    await record_audit_event(
        db,
        actor="procurement-analyst",
        action="benchmark.created",
        entity_type="pricing_benchmark",
        entity_id=benchmark.id,
        summary=(
            f"Recorded benchmark {benchmark.sku_code} at ${benchmark.quoted_unit_price:,.2f} "
            f"{benchmark.unit_type} ({benchmark.volume_tier})."
        ),
    )
    await db.commit()
    await db.refresh(benchmark)
    return PricingBenchmarkRead.model_validate(benchmark).model_copy(
        update={"vendor_name": vendor_name}
    )


@router.get("/summary", response_model=list[BenchmarkSummaryRead])
async def summarize_benchmarks(
    db: AsyncSession = Depends(get_db),
) -> list[BenchmarkSummaryRead]:
    """Return percentile summary distributions grouped by SKU."""
    return await get_benchmark_summary(db)


@router.post("/analyze", response_model=QuoteAnalyzeResponse)
async def analyze_quote(
    payload: QuoteAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
) -> QuoteAnalyzeResponse:
    """Evaluate a proposed quote price and uplift against historical benchmarks."""
    return await analyze_quote_pricing(db, payload)

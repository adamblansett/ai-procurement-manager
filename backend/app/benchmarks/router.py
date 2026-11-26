import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
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


@router.post("/import-csv")
async def import_benchmarks_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bulk-import normalized pricing benchmarks from an uploaded UTF-8 CSV file."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded CSV file is empty")
    try:
        text_data = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(text_data))
    imported_count = 0
    skipped_count = 0
    errors: list[str] = []

    for row_num, row in enumerate(reader, start=2):
        try:
            sku_code = (row.get("sku_code") or "").strip()
            sku_name = (row.get("sku_name") or "").strip()
            category = (row.get("category") or "").strip()
            unit_type = (row.get("unit_type") or "unit/year").strip()
            price = float((row.get("quoted_unit_price") or "").strip())
            if not sku_code or not sku_name or not category or price <= 0:
                raise ValueError("Missing required SKU/category/price fields")
            bm = PricingBenchmark(
                sku_code=sku_code,
                sku_name=sku_name,
                category=category,
                unit_type=unit_type,
                volume_tier=(row.get("volume_tier") or "51-250").strip(),
                quoted_unit_price=round(price, 2),
                currency=(row.get("currency") or "USD").strip() or "USD",
                annual_uplift_pct=float((row.get("annual_uplift_pct") or "0").strip()),
                discount_pct=float((row.get("discount_pct") or "0").strip()),
                source=(row.get("source") or "historical_quote").strip(),
                effective_year=int((row.get("effective_year") or "2026").strip()),
                notes=(row.get("notes") or "").strip(),
            )
            db.add(bm)
            imported_count += 1
        except Exception as exc:  # noqa: BLE001
            skipped_count += 1
            errors.append(f"Row {row_num}: {exc}")

    if imported_count > 0:
        await db.flush()
        await record_audit_event(
            db,
            actor="procurement-analyst",
            action="benchmark.csv_imported",
            entity_type="pricing_benchmark",
            entity_id="bulk-csv",
            summary=(
                f"Imported {imported_count} pricing benchmarks from CSV "
                f"({skipped_count} skipped)."
            ),
        )
        await db.commit()

    return {
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "errors": errors,
    }

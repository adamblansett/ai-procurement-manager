from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.benchmarks.models import PricingBenchmark
from app.benchmarks.schemas import (
    BenchmarkSummaryRead,
    QuoteAnalyzeRequest,
    QuoteAnalyzeResponse,
)


def _percentile(sorted_vals: list[float], p: float) -> float:
    """Compute linear-interpolated percentile (0 <= p <= 100) from sorted floats."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 2)
    rank = (p / 100.0) * (len(sorted_vals) - 1)
    low_idx = int(rank)
    high_idx = min(low_idx + 1, len(sorted_vals) - 1)
    fraction = rank - low_idx
    val = sorted_vals[low_idx] + (sorted_vals[high_idx] - sorted_vals[low_idx]) * fraction
    return round(val, 2)


def _annual_multiplier(unit_type: str) -> int:
    lowered = unit_type.lower()
    if "/month" in lowered or "per month" in lowered or "monthly" in lowered:
        return 12
    return 1


async def get_benchmark_summary(db: AsyncSession) -> list[BenchmarkSummaryRead]:
    """Aggregate benchmark pricing distributions grouped by SKU and category."""
    rows = (
        (
            await db.execute(
                select(PricingBenchmark).order_by(
                    PricingBenchmark.category.asc(), PricingBenchmark.sku_code.asc()
                )
            )
        )
        .scalars()
        .all()
    )

    grouped: dict[tuple[str, str, str, str], list[PricingBenchmark]] = defaultdict(list)
    for row in rows:
        key = (row.sku_code, row.sku_name, row.category, row.unit_type)
        grouped[key].append(row)

    summaries: list[BenchmarkSummaryRead] = []
    for (sku_code, sku_name, category, unit_type), items in grouped.items():
        prices = sorted(item.quoted_unit_price for item in items)
        avg_uplift = round(sum(item.annual_uplift_pct for item in items) / len(items), 2)
        avg_discount = round(sum(item.discount_pct for item in items) / len(items), 2)
        summaries.append(
            BenchmarkSummaryRead(
                sku_code=sku_code,
                sku_name=sku_name,
                category=category,
                unit_type=unit_type,
                sample_size=len(items),
                min_price=round(prices[0], 2),
                p25_price=_percentile(prices, 25),
                median_price=_percentile(prices, 50),
                p75_price=_percentile(prices, 75),
                max_price=round(prices[-1], 2),
                avg_uplift_pct=avg_uplift,
                avg_discount_pct=avg_discount,
            )
        )
    return summaries


async def analyze_quote_pricing(db: AsyncSession, req: QuoteAnalyzeRequest) -> QuoteAnalyzeResponse:
    """Compare a proposed unit rate and uplift clause against historical benchmarks."""
    matched: list[PricingBenchmark] = []
    matched_by = "category"

    if req.sku_code:
        sku_stmt = select(PricingBenchmark).where(PricingBenchmark.sku_code == req.sku_code)
        sku_rows = list((await db.execute(sku_stmt)).scalars().all())
        if len(sku_rows) >= 2:
            matched = sku_rows
            matched_by = "sku_code"

    if not matched:
        cat_stmt = select(PricingBenchmark).where(PricingBenchmark.category == req.category)
        cat_rows = list((await db.execute(cat_stmt)).scalars().all())
        if req.volume_tier:
            tier_rows = [r for r in cat_rows if r.volume_tier == req.volume_tier]
            if len(tier_rows) >= 2:
                matched = tier_rows
                matched_by = "category_and_tier"
        if not matched and cat_rows:
            matched = cat_rows
            matched_by = "category"
        elif not matched and req.sku_code:
            # Fall back to single exact-SKU benchmark if category had none.
            single_sku = list(
                (
                    await db.execute(
                        select(PricingBenchmark).where(PricingBenchmark.sku_code == req.sku_code)
                    )
                )
                .scalars()
                .all()
            )
            if single_sku:
                matched = single_sku
                matched_by = "sku_code"

    if not matched:
        raise HTTPException(
            status_code=404,
            detail="No historical benchmarks found matching the specified SKU or category.",
        )

    prices = sorted(r.quoted_unit_price for r in matched)
    min_price = round(prices[0], 2)
    p25_price = _percentile(prices, 25)
    median_price = _percentile(prices, 50)
    p75_price = _percentile(prices, 75)
    max_price = round(prices[-1], 2)
    avg_uplift = round(sum(r.annual_uplift_pct for r in matched) / len(matched), 2)
    avg_discount = round(sum(r.discount_pct for r in matched) / len(matched), 2)

    variance = (
        round(((req.proposed_unit_price - median_price) / median_price) * 100.0, 2)
        if median_price > 0
        else 0.0
    )
    below_or_equal = sum(1 for price in prices if price <= req.proposed_unit_price)
    percentile_rank = round((below_or_equal / len(prices)) * 100.0, 1)

    if variance <= -5.0:
        rating = "below_market"
    elif variance <= 5.0:
        rating = "competitive"
    elif variance <= 15.0:
        rating = "above_market"
    else:
        rating = "outlier_high"

    multiplier = _annual_multiplier(req.unit_type)
    estimated_annual_spend = round(req.proposed_unit_price * req.quantity * multiplier, 2)
    target_unit_price = round(min(req.proposed_unit_price, p25_price), 2)
    target_annual_spend = round(target_unit_price * req.quantity * multiplier, 2)
    potential_savings = max(0.0, round(estimated_annual_spend - target_annual_spend, 2))

    if req.proposed_uplift_pct > 5.0:
        uplift_assessment = (
            f"Proposed {req.proposed_uplift_pct:.1f}% uplift exceeds the 5.0% policy cap and "
            f"benchmark average ({avg_uplift:.1f}%). Counter with a <= 3.0% cap."
        )
    elif req.proposed_uplift_pct > avg_uplift + 1.0:
        uplift_assessment = (
            f"Proposed {req.proposed_uplift_pct:.1f}% uplift is above the benchmark average "
            f"({avg_uplift:.1f}%). Request matching the {avg_uplift:.1f}% historical baseline."
        )
    else:
        uplift_assessment = (
            f"Proposed {req.proposed_uplift_pct:.1f}% uplift is aligned with historical peer "
            f"contracts (avg {avg_uplift:.1f}%)."
        )

    if rating in {"above_market", "outlier_high"}:
        negotiation_recommendation = (
            f"Quote is {variance:+.1f}% vs market median (${median_price:,.2f}). "
            f"Counter at P25 (${p25_price:,.2f} {req.unit_type}) to unlock "
            f"${potential_savings:,.2f}/yr in savings."
        )
    elif rating == "competitive":
        negotiation_recommendation = (
            f"Unit rate is competitive ({variance:+.1f}% vs median ${median_price:,.2f}). "
            f"Push for P25 (${p25_price:,.2f}) or multi-year uplift cap for an extra "
            f"${potential_savings:,.2f}/yr."
        )
    else:
        negotiation_recommendation = (
            f"Strong pricing ({variance:+.1f}% vs median ${median_price:,.2f}). "
            "Lock in current rate across a multi-year term with <= 3% uplift protection."
        )

    return QuoteAnalyzeResponse(
        matched_by=matched_by,
        sample_size=len(matched),
        min_price=min_price,
        p25_price=p25_price,
        median_price=median_price,
        p75_price=p75_price,
        max_price=max_price,
        avg_uplift_pct=avg_uplift,
        avg_discount_pct=avg_discount,
        proposed_unit_price=round(req.proposed_unit_price, 2),
        variance_vs_median_pct=variance,
        percentile_rank=percentile_rank,
        rating=rating,  # type: ignore[arg-type]
        estimated_annual_spend=estimated_annual_spend,
        target_unit_price=target_unit_price,
        target_annual_spend=target_annual_spend,
        potential_annual_savings=potential_savings,
        uplift_assessment=uplift_assessment,
        negotiation_recommendation=negotiation_recommendation,
    )

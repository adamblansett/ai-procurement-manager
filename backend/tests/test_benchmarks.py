import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_benchmark_crud_summary_and_quote_analysis(client: AsyncClient) -> None:
    samples = [
        ("CRM-PRO-SEAT", "CRM Pro Seat", "SaaS Applications", "seat/month", 100.0, 2.0, 20.0),
        ("CRM-PRO-SEAT", "CRM Pro Seat", "SaaS Applications", "seat/month", 120.0, 3.0, 15.0),
        ("CRM-PRO-SEAT", "CRM Pro Seat", "SaaS Applications", "seat/month", 140.0, 4.0, 10.0),
    ]
    for sku, name, cat, unit, price, uplift, disc in samples:
        resp = await client.post(
            "/api/v1/benchmarks",
            json={
                "sku_code": sku,
                "sku_name": name,
                "category": cat,
                "unit_type": unit,
                "volume_tier": "51-250",
                "quoted_unit_price": price,
                "annual_uplift_pct": uplift,
                "discount_pct": disc,
                "source": "executed_contract",
                "effective_year": 2026,
            },
        )
        assert resp.status_code == 201

    summary_resp = await client.get("/api/v1/benchmarks/summary")
    assert summary_resp.status_code == 200
    summaries = summary_resp.json()
    assert len(summaries) == 1
    assert summaries[0]["sample_size"] == 3
    assert summaries[0]["min_price"] == 100.0
    assert summaries[0]["p25_price"] == 110.0
    assert summaries[0]["median_price"] == 120.0
    assert summaries[0]["p75_price"] == 130.0
    assert summaries[0]["max_price"] == 140.0

    # High outlier quote with aggressive uplift
    high_resp = await client.post(
        "/api/v1/benchmarks/analyze",
        json={
            "sku_code": "CRM-PRO-SEAT",
            "category": "SaaS Applications",
            "unit_type": "seat/month",
            "quantity": 100,
            "proposed_unit_price": 150.0,
            "proposed_uplift_pct": 8.5,
        },
    )
    assert high_resp.status_code == 200
    high = high_resp.json()
    assert high["rating"] == "outlier_high"
    assert high["variance_vs_median_pct"] == 25.0
    assert high["target_unit_price"] == 110.0
    assert high["estimated_annual_spend"] == 180000.0
    assert high["potential_annual_savings"] == 48000.0
    assert "exceeds the 5.0% policy cap" in high["uplift_assessment"]

    # Below-market quote
    low_resp = await client.post(
        "/api/v1/benchmarks/analyze",
        json={
            "sku_code": "CRM-PRO-SEAT",
            "category": "SaaS Applications",
            "unit_type": "seat/month",
            "quantity": 100,
            "proposed_unit_price": 105.0,
            "proposed_uplift_pct": 2.0,
        },
    )
    assert low_resp.status_code == 200
    low = low_resp.json()
    assert low["rating"] == "below_market"
    assert low["potential_annual_savings"] == 0.0

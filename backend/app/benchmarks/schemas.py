from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PricingBenchmarkCreate(BaseModel):
    vendor_id: str | None = None
    sku_code: str = Field(min_length=2, max_length=80)
    sku_name: str = Field(min_length=2, max_length=160)
    category: str = Field(min_length=2, max_length=80)
    unit_type: str = Field(min_length=2, max_length=48)
    volume_tier: Literal["1-50", "51-250", "251-1000", "1000+"] = "51-250"
    quoted_unit_price: float = Field(gt=0.0)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    annual_uplift_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    discount_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    source: Literal["historical_quote", "executed_contract", "market_index"] = "historical_quote"
    effective_year: int = Field(default=2026, ge=2020, le=2040)
    notes: str = ""


class PricingBenchmarkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vendor_id: str | None
    vendor_name: str = ""
    sku_code: str
    sku_name: str
    category: str
    unit_type: str
    volume_tier: str
    quoted_unit_price: float
    currency: str
    annual_uplift_pct: float
    discount_pct: float
    source: str
    effective_year: int
    notes: str
    created_at: datetime


class BenchmarkSummaryRead(BaseModel):
    sku_code: str
    sku_name: str
    category: str
    unit_type: str
    sample_size: int
    min_price: float
    p25_price: float
    median_price: float
    p75_price: float
    max_price: float
    avg_uplift_pct: float
    avg_discount_pct: float


class QuoteAnalyzeRequest(BaseModel):
    sku_code: str | None = None
    category: str = Field(min_length=2, max_length=80)
    unit_type: str = Field(default="seat/month", min_length=2, max_length=48)
    volume_tier: Literal["1-50", "51-250", "251-1000", "1000+"] | None = None
    quantity: int = Field(default=100, ge=1)
    proposed_unit_price: float = Field(gt=0.0)
    proposed_uplift_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class QuoteAnalyzeResponse(BaseModel):
    matched_by: str
    sample_size: int
    min_price: float
    p25_price: float
    median_price: float
    p75_price: float
    max_price: float
    avg_uplift_pct: float
    avg_discount_pct: float
    proposed_unit_price: float
    variance_vs_median_pct: float
    percentile_rank: float
    rating: Literal["below_market", "competitive", "above_market", "outlier_high"]
    estimated_annual_spend: float
    target_unit_price: float
    target_annual_spend: float
    potential_annual_savings: float
    uplift_assessment: str
    negotiation_recommendation: str
